#!/usr/bin/env python3
"""Auto-confirm Experience League URLs for pending feature-map features and merge
the confirmed ones into the governed feature-map.

For every feature still marked URL-unconfirmed in the scratch surface drafts, this
queries the local aem_guides corpus; if the top hit is an AEM Guides Experience
League page under the distance threshold, it reports the confirmation. It merges
only drafts whose curation_status is already APPROVED; PENDING_APPROVAL drafts
remain pending for Human review. Eligible entries are conformed to strict
feature_map governance and merged into data/aem_feature_map.json. Features whose
page is still not in the corpus stay unconfirmed (honest - no fabricated URL).
Run AFTER refreshing the crawl (scripts/vm_ingest_review_authoring_publishing_gaps.sh).

Default is a dry run (report only). Pass --apply to write the merged map.

    python scripts/confirm_and_merge_feature_urls.py            # dry run
    python scripts/confirm_and_merge_feature_urls.py --apply    # write + validate
"""
from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
SKILL = REPO / ".codex" / "skills" / "test-plan-generation"
FEATURE_MAP = SKILL / "data" / "aem_feature_map.json"
DISTANCE_MAX = 0.35  # honesty threshold: a weak hit must not auto-stamp a URL
MAX_DRAFT_BYTES = 1024 * 1024

# scratch drafts holding the pending (url_confirmed=false) features
DRAFTS = {
    "PUBLISHING_OUTPUT": "publishing_surface_draft.json",
    "AUTHORING": "authoring_surface_draft.json",
    "REVIEW": "review_surface_draft.json",
    "BASELINE": "baseline_surface_draft.json",
    "EDITOR_OXYGEN": "editor_oxygen_surface_draft.json",
    "SECURITY": "security_surface_draft.json",
}


def _scratch_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    # default: the session scratchpad gb_run sibling used for these drafts
    # Repo-tracked drafts so this runs on any box (VM included), not just the authoring session.
    return (REPO / "scripts" / "feature_map_drafts").resolve()


def _distance_arg(value: str) -> float:
    """Parse a bounded distance without allowing the honesty ceiling to rise."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("distance must be a number") from exc
    if not math.isfinite(parsed) or not 0.0 <= parsed <= DISTANCE_MAX:
        raise argparse.ArgumentTypeError(
            f"distance must be finite and between 0 and {DISTANCE_MAX}"
        )
    return parsed


def _is_guides_url(value: object) -> bool:
    """Accept only canonical HTTPS Experience League AEM Guides document URLs."""
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.netloc == "experienceleague.adobe.com"
        and parsed.path.startswith("/en/docs/experience-manager-guides/")
        and not parsed.query
        and not parsed.fragment
    )


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
    rows = v.query_collection(v.CHROMA_COLLECTION_AEM_GUIDES, emb, k=1) or []
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    row = rows[0]
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        return None
    url = str(metadata.get("url") or metadata.get("source") or "").strip()
    try:
        distance = float(row.get("distance", 1.0))
    except (TypeError, ValueError):
        return None
    if not _is_guides_url(url) or not math.isfinite(distance) or distance < 0.0:
        return None
    return url, str(metadata.get("title") or ""), distance


def _load_feature_map(fm) -> tuple[dict, list[str]]:
    data = json.loads(FEATURE_MAP.read_text(encoding="utf-8"))
    return data, fm.validate_repository_map(str(FEATURE_MAP))


def _load_draft(
    path: Path,
    scratch: Path,
    expected_surface: str,
) -> tuple[dict | None, str | None]:
    """Load one bounded, direct-child JSON draft without following symlinks."""
    try:
        if path.is_symlink():
            return None, "draft symlinks are not allowed"
        resolved = path.resolve(strict=True)
        if resolved.parent != scratch:
            return None, "draft must be a direct child of the scratch directory"
        if resolved.stat().st_size > MAX_DRAFT_BYTES:
            return None, f"draft exceeds {MAX_DRAFT_BYTES} bytes"
        draft = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, f"draft cannot be read as JSON: {exc}"
    if not isinstance(draft, dict):
        return None, "draft root must be an object"
    if draft.get("surface") != expected_surface:
        return None, f"draft surface must be {expected_surface}"
    if str(draft.get("curation_status", "")).strip().upper() not in {
        "APPROVED",
        "PENDING_APPROVAL",
    }:
        return None, "draft curation_status must be APPROVED or PENDING_APPROVAL"
    if not isinstance(draft.get("match"), list) or not isinstance(
        draft.get("native_features"), list
    ):
        return None, "draft match and native_features must be lists"
    return draft, None


def _write_validated_map(data: dict, fm) -> list[str]:
    """Validate a same-directory temporary file, then atomically replace the map."""
    payload = json.dumps(data, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=FEATURE_MAP.parent,
            prefix=f".{FEATURE_MAP.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        problems = fm.validate_repository_map(str(temporary_path))
        if problems:
            return problems
        os.chmod(temporary_path, stat.S_IMODE(FEATURE_MAP.stat().st_mode))
        os.replace(temporary_path, FEATURE_MAP)
        temporary_path = None
        return []
    except OSError as exc:
        return [f"feature map could not be written atomically: {exc}"]
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write the merged map (default: dry run)")
    ap.add_argument("--scratch-dir", default=None, help="dir holding the *_surface_draft.json files")
    ap.add_argument(
        "--distance-max",
        type=_distance_arg,
        default=DISTANCE_MAX,
        help=f"maximum accepted distance (0..{DISTANCE_MAX}; cannot raise the honesty ceiling)",
    )
    args = ap.parse_args(argv)

    sys.path.insert(0, str(SKILL / "scripts"))
    import feature_map as fm

    scratch = _scratch_dir(args.scratch_dir)
    if not scratch.is_dir():
        print(
            "REFUSING: scratch directory does not exist or is not a directory: "
            f"{scratch}"
        )
        return 2
    data, pre_problems = _load_feature_map(fm)
    if pre_problems:
        print("REFUSING: live feature-map already fails governance:", pre_problems)
        return 2
    surfaces_by_name = {s["surface"]: s for s in data["surfaces"]}

    confirmed, merged, approval_pending = [], [], []
    still_pending, input_failures = [], []
    for surface_name, draft_file in DRAFTS.items():
        path = scratch / draft_file
        if not path.is_file():
            print(f"(skip {surface_name}: draft not found at {path})")
            input_failures.append(f"{surface_name}: draft not found")
            continue
        draft, draft_problem = _load_draft(path, scratch, surface_name)
        if draft_problem or draft is None:
            print(f"(skip {surface_name}: {draft_problem})")
            input_failures.append(f"{surface_name}: {draft_problem}")
            continue
        draft_is_human_approved = (
            str(draft.get("curation_status", "")).strip().upper() == "APPROVED"
        )
        for feature_index, feat in enumerate(draft["native_features"], start=1):
            if not isinstance(feat, dict):
                still_pending.append(
                    (surface_name, f"feature #{feature_index}", "feature must be an object")
                )
                continue
            if feat.get("url_confirmed"):
                continue
            feature = str(feat.get("feature", "")).strip()
            candidate_template = str(feat.get("candidate_template", "")).strip()
            shared_flows = feat.get("shared_flows")
            if (
                not feature
                or not candidate_template
                or not isinstance(shared_flows, list)
                or not shared_flows
                or any(not isinstance(flow, str) or not flow.strip() for flow in shared_flows)
            ):
                still_pending.append(
                    (
                        surface_name,
                        feature or f"feature #{feature_index}",
                        "incomplete feature contract",
                    )
                )
                continue
            axis = str(feat.get("implied_dimension_axis", "")).upper()
            if axis not in fm.VALID_AXES:
                still_pending.append((surface_name, feature, f"invalid axis {axis}"))
                continue
            query = f"{feature} {candidate_template[:80]}"
            hit = _query_top(query)
            if not hit:
                still_pending.append((surface_name, feature, "no confident corpus hit"))
                continue
            url, _title, dist = hit
            if dist > args.distance_max:
                still_pending.append(
                    (
                        surface_name,
                        feature,
                        f"top hit distance {dist:.3f} exceeds {args.distance_max:.3f}: {url}",
                    )
                )
                continue
            confirmed.append((surface_name, feature, round(dist, 3), url))
            if not draft_is_human_approved:
                approval_pending.append((surface_name, feature, round(dist, 3), url))
                still_pending.append(
                    (
                        surface_name,
                        feature,
                        "URL confirmed, but the draft still awaits Human approval",
                    )
                )
                continue
            conformed = {
                "feature": feature,
                "shared_flows": [flow.strip() for flow in shared_flows],
                "implied_dimension_axis": axis,
                "candidate_template": candidate_template,
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
            existing_features = {
                str(existing.get("feature", "")).strip().casefold()
                for existing in surf["native_features"]
                if isinstance(existing, dict)
            }
            if conformed["feature"].casefold() not in existing_features:
                surf["native_features"].append(conformed)
                merged.append((surface_name, feature, round(dist, 3), url))

    print(f"\n=== CONFIRMED {len(confirmed)} ===")
    for s, f, d, u in confirmed:
        print(f"  [{s}] {f}  (dist {d})  {u}")
    print(f"\n=== STILL PENDING {len(still_pending)} ===")
    for s, f, why in still_pending:
        print(f"  [{s}] {f}  - {why}")

    if input_failures:
        print("\nREFUSING: one or more configured drafts are missing or invalid:")
        for failure in input_failures:
            print(f"  - {failure}")
        return 2

    if args.apply and merged:
        post = _write_validated_map(data, fm)
        if post:
            print("\nREFUSING: governance failed before atomic merge:", post)
            return 3
        print(f"\nAPPLIED: merged {len(merged)} feature(s); feature-map now has "
              f"{len(data['surfaces'])} surfaces. Governance clean.")
        print("NEXT: sync copies+globals, bump the surface-count self-test if a new surface was added, run self-tests, commit.")
    elif merged:
        print(f"\nDRY RUN: {len(merged)} feature(s) would merge. Re-run with --apply to write.")
    elif approval_pending:
        print(
            f"\nNO MERGE: {len(approval_pending)} URL-confirmed feature(s) still await "
            "Human approval."
        )
    elif confirmed:
        print("\nAll confirmed features are already present; no map change is needed.")
    else:
        print("\nNothing confirmable yet - refresh the crawl "
              "(scripts/vm_ingest_review_authoring_publishing_gaps.sh) first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
