#!/usr/bin/env python3
"""Discover Experience League URL candidates and merge only Human-approved sources.

For every feature that is not already active, this queries the local aem_guides
corpus and reports a candidate when the top AEM Guides Experience League hit is
within the distance threshold. Similarity is discovery evidence only: it never
sets Human approval and never writes a discovered URL into the governed map.

A feature becomes merge-eligible only when its draft entry explicitly contains
``approval_status=HUMAN_APPROVED``, ``url_confirmed=true``, and one or more valid
``reference_urls``. This per-feature contract allows a partially reviewed surface
to remain ``PENDING_APPROVAL`` while its individually approved entries are merged.
Run after refreshing the crawl
(``scripts/vm_ingest_review_authoring_publishing_gaps.sh``).

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
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
SKILL = REPO / ".codex" / "skills" / "test-plan-generation"
FEATURE_MAP = SKILL / "data" / "aem_feature_map.json"
DISTANCE_MAX = 0.35  # honesty threshold: a weak hit must not auto-stamp a URL
MAX_DRAFT_BYTES = 1024 * 1024
HUMAN_APPROVED = "HUMAN_APPROVED"
UNAPPROVED_DISCOVERY_STATUSES = {"", "PENDING_APPROVAL", "APPROVED_URL_UNCONFIRMED"}

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
    raw_path = parsed.path
    lowered_path = raw_path.casefold()
    decoded_path = unquote(raw_path)
    path_segments = decoded_path.split("/")
    has_unsafe_segment = any(segment in {".", ".."} for segment in path_segments)
    has_encoded_path_control = any(
        token in lowered_path for token in ("%2e", "%2f", "%5c")
    )
    has_percent_encoding = "%" in raw_path
    guides_prefix = "/en/docs/experience-manager-guides/"
    document_path = (
        decoded_path[len(guides_prefix) :].strip("/")
        if decoded_path.startswith(guides_prefix)
        else ""
    )
    return (
        parsed.scheme == "https"
        and parsed.netloc == "experienceleague.adobe.com"
        and decoded_path.startswith(guides_prefix)
        and bool(document_path)
        and not has_unsafe_segment
        and not has_encoded_path_control
        and not has_percent_encoding
        and "\\" not in decoded_path
        and not parsed.query
        and not parsed.fragment
    )


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
    seen_feature_names: set[str] = set()
    for feature in draft["native_features"]:
        if not isinstance(feature, dict):
            continue
        feature_name = str(feature.get("feature", "")).strip()
        if not feature_name:
            continue
        feature_key = feature_name.casefold()
        if feature_key in seen_feature_names:
            return None, f"duplicate feature name in draft: {feature_name}"
        seen_feature_names.add(feature_key)
    return draft, None


def _approved_source(
    feature: dict,
) -> tuple[tuple[str, list[str]] | None, str | None]:
    """Return an explicitly Human-approved source, or a validation problem.

    Empty approval fields mean that the feature is still a discovery candidate.
    Partially populated approval fields fail closed instead of being inferred.
    """
    approval = str(feature.get("approval_status", "")).strip().upper()
    url_confirmed = feature.get("url_confirmed", False)
    reference = str(feature.get("reference", "")).strip()
    reference_urls = feature.get("reference_urls", [])
    if approval in UNAPPROVED_DISCOVERY_STATUSES:
        if url_confirmed is False and not reference_urls:
            return None, None
        return None, "an unapproved feature cannot declare a confirmed source"
    if approval != HUMAN_APPROVED:
        return None, f"approval_status must be {HUMAN_APPROVED}"
    if url_confirmed is not True:
        return None, "url_confirmed must be true for a Human-approved feature"
    if not reference.startswith("Experience League "):
        return None, "reference must start with 'Experience League '"
    if (
        not isinstance(reference_urls, list)
        or not reference_urls
        or any(not _is_guides_url(url) for url in reference_urls)
    ):
        return None, "reference_urls must contain only canonical AEM Guides Experience League URLs"
    return (reference, [str(url).strip() for url in reference_urls]), None


def _conformed_feature(
    feature: dict,
    *,
    axis: str,
    reference: str,
    reference_urls: list[str],
) -> dict:
    """Build the governed feature-map representation from an approved draft entry."""
    return {
        "feature": str(feature["feature"]).strip(),
        "shared_flows": [str(flow).strip() for flow in feature["shared_flows"]],
        "implied_dimension_axis": axis,
        "candidate_template": str(feature["candidate_template"]).strip(),
        "reference": reference,
        "reference_urls": list(reference_urls),
        "approval_status": HUMAN_APPROVED,
    }


def _legacy_confirmed_source(feature: dict) -> list[str] | None:
    """Recognize a valid pre-contract source without making it merge-eligible.

    Older tracked drafts recorded Human approval and a canonical URL but used a
    descriptive reference label. Those entries remain reportable and read-only;
    only the stricter current contract can authorize a new map write.
    """
    approval = str(feature.get("approval_status", "")).strip().upper()
    reference = str(feature.get("reference", "")).strip()
    reference_urls = feature.get("reference_urls", [])
    if (
        approval != HUMAN_APPROVED
        or feature.get("url_confirmed") is not True
        or not reference
        or reference.startswith("Experience League ")
        or not isinstance(reference_urls, list)
        or not reference_urls
        or any(not _is_guides_url(url) for url in reference_urls)
    ):
        return None
    return [str(url).strip() for url in reference_urls]


def _active_feature(surface: dict | None, feature_name: str) -> dict | None:
    """Find one active feature by its stable case-insensitive name."""
    if not isinstance(surface, dict):
        return None
    native_features = surface.get("native_features", [])
    if not isinstance(native_features, list):
        return None
    key = feature_name.casefold()
    return next(
        (
            item
            for item in native_features
            if isinstance(item, dict)
            and str(item.get("feature", "")).strip().casefold() == key
        ),
        None,
    )


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

    already_active, legacy_confirmed, merge_eligible, url_candidates = [], [], [], []
    still_unresolved, input_failures = [], []
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
        seen_draft_features: set[str] = set()
        for feature_index, feat in enumerate(draft["native_features"], start=1):
            if not isinstance(feat, dict):
                input_failures.append(
                    f"{surface_name} feature #{feature_index}: feature must be an object"
                )
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
                input_failures.append(
                    f"{surface_name} {feature or f'feature #{feature_index}'}: "
                    "incomplete feature contract"
                )
                continue
            feature_key = feature.casefold()
            if feature_key in seen_draft_features:
                input_failures.append(
                    f"{surface_name} {feature}: duplicate feature name in draft"
                )
                continue
            seen_draft_features.add(feature_key)
            axis = str(feat.get("implied_dimension_axis", "")).upper()
            if axis not in fm.VALID_AXES:
                input_failures.append(f"{surface_name} {feature}: invalid axis {axis}")
                continue

            surf = surfaces_by_name.get(surface_name)
            active = _active_feature(surf, feature)
            if active is not None:
                approved_source, source_problem = _approved_source(feat)
                if source_problem:
                    if _legacy_confirmed_source(feat) is None:
                        input_failures.append(
                            f"{surface_name} {feature}: {source_problem}"
                        )
                        continue
                elif approved_source is not None:
                    reference, reference_urls = approved_source
                    expected = _conformed_feature(
                        feat,
                        axis=axis,
                        reference=reference,
                        reference_urls=reference_urls,
                    )
                    if active != expected:
                        input_failures.append(
                            f"{surface_name} {feature}: active map differs from its "
                            "Human-approved draft entry"
                        )
                        continue
                already_active.append(
                    (
                        surface_name,
                        feature,
                        list(active.get("reference_urls", [])),
                    )
                )
                continue

            legacy_source_urls = _legacy_confirmed_source(feat)
            if legacy_source_urls is not None:
                legacy_confirmed.append((surface_name, feature, legacy_source_urls))
                continue

            approved_source, source_problem = _approved_source(feat)
            if source_problem:
                input_failures.append(f"{surface_name} {feature}: {source_problem}")
                continue

            if approved_source is not None:
                reference, reference_urls = approved_source
                conformed = _conformed_feature(
                    feat,
                    axis=axis,
                    reference=reference,
                    reference_urls=reference_urls,
                )
                if surf is None:
                    surf = {
                        "surface": surface_name,
                        "match": list(draft.get("match", [])),
                        "native_features": [],
                    }
                    data["surfaces"].append(surf)
                    surfaces_by_name[surface_name] = surf
                surf["native_features"].append(conformed)
                merge_eligible.append((surface_name, feature, reference_urls))
                continue

            query = f"{feature} {candidate_template[:80]}"
            try:
                hit = _query_top(query)
            except Exception as exc:  # advisory lookup must fail open without leaking details
                still_unresolved.append(
                    (
                        surface_name,
                        feature,
                        f"retrieval unavailable ({type(exc).__name__})",
                    )
                )
                continue
            if not hit:
                still_unresolved.append((surface_name, feature, "no eligible top corpus hit"))
                continue
            url, _title, dist = hit
            if dist > args.distance_max:
                still_unresolved.append(
                    (
                        surface_name,
                        feature,
                        f"top hit distance {dist:.3f} exceeds {args.distance_max:.3f}: {url}",
                    )
                )
                continue
            url_candidates.append((surface_name, feature, round(dist, 3), url))

    print(f"\n=== ALREADY ACTIVE {len(already_active)} ===")
    for surface_name, feature, urls in already_active:
        suffix = f"  {'; '.join(urls)}" if urls else ""
        print(f"  [{surface_name}] {feature}{suffix}")
    print(f"\n=== LEGACY SOURCE CONFIRMATIONS (NO MERGE) {len(legacy_confirmed)} ===")
    for surface_name, feature, urls in legacy_confirmed:
        print(f"  [{surface_name}] {feature}  {'; '.join(urls)}")
    print(f"\n=== HUMAN-APPROVED MERGE ELIGIBLE {len(merge_eligible)} ===")
    for surface_name, feature, urls in merge_eligible:
        print(f"  [{surface_name}] {feature}  {'; '.join(urls)}")
    print(f"\n=== URL CANDIDATES AWAITING HUMAN APPROVAL {len(url_candidates)} ===")
    for surface_name, feature, distance, url in url_candidates:
        print(f"  [{surface_name}] {feature}  (dist {distance})  {url}")
    print(f"\n=== STILL UNRESOLVED {len(still_unresolved)} ===")
    for s, f, why in still_unresolved:
        print(f"  [{s}] {f}  - {why}")

    if input_failures:
        print("\nREFUSING: one or more configured drafts are missing or invalid:")
        for failure in input_failures:
            print(f"  - {failure}")
        return 2

    if args.apply and merge_eligible:
        post = _write_validated_map(data, fm)
        if post:
            print("\nREFUSING: governance failed before atomic merge:", post)
            return 3
        print(f"\nAPPLIED: merged {len(merge_eligible)} Human-approved feature(s); "
              "feature-map now has "
              f"{len(data['surfaces'])} surfaces. Governance clean.")
        print("NEXT: sync copies+globals, bump the surface-count self-test if a new surface was added, run self-tests, commit.")
    elif merge_eligible:
        print(
            f"\nDRY RUN: {len(merge_eligible)} Human-approved feature(s) would merge. "
            "Re-run with --apply to write."
        )
    elif url_candidates:
        print(
            f"\nNO MERGE: {len(url_candidates)} discovered URL candidate(s) still "
            "require explicit Human source approval in their draft entries."
        )
    elif (already_active or legacy_confirmed) and not still_unresolved:
        print("\nAll configured features are already active; no map change is needed.")
    else:
        print("\nNo new Human-approved feature is merge-eligible. Review unresolved "
              "features or refresh the crawl before retrying.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
