"""Curated AEM/Guides feature-map discovery (UACDISCOVER-03).

The checked-in map is a human-approved domain checklist. Matching evidence emits
only ``INVESTIGATION_CANDIDATE`` coverage hypotheses. A map entry is never Jira
scope, implementation proof, acceptance truth, or a direct path to an AC.

The loader is deliberately fail-open for plan generation: a missing, malformed,
unapproved, or unsupported map contributes no candidates and never blocks the
canonical runtime.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "aem-guides-feature-map-v1"
APPROVED_STATUS = "HUMAN_APPROVED"
GENERATOR = "FEATURE_MAP"
EXPERIENCE_LEAGUE_PREFIX = "https://experienceleague.adobe.com/"
VALID_AXES = {
    "VALUE_SET_CHANNEL",
    "CODE_PATH_CONSUMER",
    "OUTPUT_PRESET",
    "TOPIC_TYPE",
    "TERMINAL_STATE",
    "LIFECYCLE",
    "CONFIG_BRANCH",
    "PERMISSION_ROLE",
    "MIGRATION_PATH",
    "NEGATIVE_BOUNDARY",
    "ENTRY_POINT",
    "REPRO_DIMENSION",
    "DOWNSTREAM_REGRESSION",
}
COVERAGE_DIMENSION_BY_AXIS = {
    "VALUE_SET_CHANNEL": "CONTRACT_BOUNDARY",
    "CODE_PATH_CONSUMER": "CONSUMER",
    "OUTPUT_PRESET": "PUBLISHING_MODE",
    "TOPIC_TYPE": "TYPE_ABSTRACTION",
    "TERMINAL_STATE": "STATE_PARTITION",
    "LIFECYCLE": "LIFECYCLE",
    "CONFIG_BRANCH": "CONFIGURATION",
    "PERMISSION_ROLE": "STATE_PARTITION",
    "MIGRATION_PATH": "BACKWARD_COMPATIBILITY",
    "NEGATIVE_BOUNDARY": "STATE_PARTITION",
    "ENTRY_POINT": "CONTRACT_BOUNDARY",
    "REPRO_DIMENSION": "NFR_RISK",
    "DOWNSTREAM_REGRESSION": "DOWNSTREAM_REGRESSION",
}
_SURFACE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def _default_map_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "aem_feature_map.json"


def _empty_map() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "curation_status": "UNAVAILABLE",
        "authority": "Adobe Experience League",
        "surfaces": [],
    }


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _approved_feature(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    feature = str(value.get("feature", "")).strip()
    axis = str(value.get("implied_dimension_axis", "")).strip().upper()
    template = str(value.get("candidate_template", "")).strip()
    reference = str(value.get("reference", "")).strip()
    shared_flows = _strings(value.get("shared_flows"))
    reference_urls = _strings(value.get("reference_urls"))
    approved = str(value.get("approval_status", "")).strip().upper()
    if (
        approved != APPROVED_STATUS
        or not feature
        or axis not in VALID_AXES
        or not template
        or not shared_flows
        or not reference.startswith("Experience League ")
        or not reference_urls
        or any(not url.startswith(EXPERIENCE_LEAGUE_PREFIX) for url in reference_urls)
    ):
        return None
    return {
        "feature": feature,
        "shared_flows": shared_flows,
        "implied_dimension_axis": axis,
        "candidate_template": template,
        "reference": reference,
        "reference_urls": reference_urls,
        "approval_status": APPROVED_STATUS,
    }


def load_map(path: str | Path | None = None) -> dict[str, Any]:
    """Load and defensively sanitize the human-approved feature map.

    Invalid content is treated as an unavailable advisory source. The caller never
    has to catch file, JSON, schema, or validation errors.
    """
    try:
        map_path = Path(path) if path is not None else _default_map_path()
        raw = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return _empty_map()
    if not isinstance(raw, dict):
        return _empty_map()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return _empty_map()
    if str(raw.get("curation_status", "")).strip().upper() != APPROVED_STATUS:
        return _empty_map()
    if raw.get("authority") != "Adobe Experience League":
        return _empty_map()
    raw_surfaces = raw.get("surfaces")
    if not isinstance(raw_surfaces, list):
        return _empty_map()

    surfaces: list[dict[str, Any]] = []
    for value in raw_surfaces:
        if not isinstance(value, dict):
            continue
        surface = str(value.get("surface", "")).strip().upper()
        match = _strings(value.get("match"))
        raw_features = value.get("native_features")
        if not isinstance(raw_features, list):
            continue
        features = [
            approved
            for item in raw_features
            if (approved := _approved_feature(item)) is not None
        ]
        if not _SURFACE_RE.fullmatch(surface) or not match or not features:
            continue
        surfaces.append(
            {
                "surface": surface,
                "match": match,
                "native_features": features,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "curation_status": APPROVED_STATUS,
        "authority": "Adobe Experience League",
        "surfaces": surfaces,
    }


def validate_repository_map(path: str | Path | None = None) -> list[str]:
    """Strictly validate checked-in curation without changing runtime fail-open behavior."""
    try:
        map_path = Path(path) if path is not None else _default_map_path()
        raw_text = map_path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"feature map cannot be read as JSON: {exc}"]
    problems: list[str] = []
    if not isinstance(raw, dict):
        return ["feature map root must be an object"]
    if raw.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version must be {SCHEMA_VERSION}")
    if str(raw.get("curation_status", "")).strip().upper() != APPROVED_STATUS:
        problems.append(f"curation_status must be {APPROVED_STATUS}")
    if raw.get("authority") != "Adobe Experience League":
        problems.append("authority must be Adobe Experience League")
    if _JIRA_KEY_RE.search(raw_text):
        problems.append("feature map must not contain a Jira key")
    raw_surfaces = raw.get("surfaces")
    if not isinstance(raw_surfaces, list) or not raw_surfaces:
        problems.append("surfaces must be a non-empty list")
        return problems

    seen_surfaces: set[str] = set()
    for surface_index, value in enumerate(raw_surfaces):
        tag = f"surfaces[{surface_index}]"
        if not isinstance(value, dict):
            problems.append(f"{tag} must be an object")
            continue
        surface = str(value.get("surface", "")).strip()
        if not _SURFACE_RE.fullmatch(surface):
            problems.append(f"{tag}.surface must be a generic upper-snake-case name")
        elif surface in seen_surfaces:
            problems.append(f"duplicate surface {surface}")
        seen_surfaces.add(surface)
        match = value.get("match")
        match_tokens = _strings(match)
        if not isinstance(match, list) or not match_tokens:
            problems.append(f"{tag}.match must be a non-empty string list")
        if len({token.casefold() for token in match_tokens}) != len(match_tokens):
            problems.append(f"{tag}.match contains duplicate phrases")
        for token in match_tokens:
            if (
                token != token.casefold()
                or any(mark in token for mark in ("/", "\\", "::", "(", ")", "."))
                or re.search(r"[a-z][a-z0-9]*[A-Z]", token)
            ):
                problems.append(f"{tag}.match contains non-generic phrase {token!r}")

        raw_features = value.get("native_features")
        if not isinstance(raw_features, list) or not raw_features:
            problems.append(f"{tag}.native_features must be a non-empty list")
            continue
        seen_features: set[str] = set()
        for feature_index, feature in enumerate(raw_features):
            feature_tag = f"{tag}.native_features[{feature_index}]"
            approved = _approved_feature(feature)
            if approved is None:
                problems.append(
                    f"{feature_tag} must be Human-approved, complete, and cite only Experience League"
                )
                continue
            feature_key = approved["feature"].casefold()
            if feature_key in seen_features:
                problems.append(f"{tag} contains duplicate feature {approved['feature']!r}")
            seen_features.add(feature_key)
    return problems


def _normalise_pairs(evidence_pairs: object) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not isinstance(evidence_pairs, (list, tuple)):
        return pairs
    for index, item in enumerate(evidence_pairs, start=1):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            label, body = item[0], item[1]
        elif isinstance(item, dict):
            label = item.get("label") or item.get("id") or f"evidence-{index}"
            body = item.get("text") or item.get("document") or item.get("note") or ""
        else:
            continue
        text = str(body).strip()
        if text:
            pairs.append((str(label).strip() or f"evidence-{index}", text))
    return pairs


def _equivalence_feature(feature: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", feature.casefold()).strip("-")


def candidates_for(
    evidence_pairs: object,
    map_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Emit human-curated ``FEATURE_MAP`` investigation candidates on a match."""
    pairs = _normalise_pairs(evidence_pairs)
    if not pairs:
        return []
    feature_map = load_map(map_path)
    candidates: list[dict[str, Any]] = []
    for surface in feature_map["surfaces"]:
        match_tokens = [token.casefold() for token in surface["match"]]
        hit_labels: list[str] = []
        hit_tokens: list[str] = []
        for label, text in pairs:
            low = text.casefold()
            matched = [token for token in match_tokens if token in low]
            if not matched:
                continue
            if label not in hit_labels:
                hit_labels.append(label)
            for token in matched:
                if token not in hit_tokens:
                    hit_tokens.append(token)
        if not hit_labels:
            continue

        for feature in surface["native_features"]:
            feature_name = feature["feature"]
            reference = feature["reference"]
            candidates.append(
                {
                    "hypothesis_id": "",
                    "dimension": COVERAGE_DIMENSION_BY_AXIS[feature["implied_dimension_axis"]],
                    "implied_dimension_axis": feature["implied_dimension_axis"],
                    "candidate": feature["candidate_template"],
                    "reason": (
                        f"FEATURE_MAP {surface['surface']} matched the current evidence; "
                        f"investigate native feature '{feature_name}'"
                    ),
                    "technical_basis": [
                        f"FEATURE_MAP:{surface['surface']}:{feature_name}",
                        f"reference:{reference}",
                        *(f"reference_url:{url}" for url in feature["reference_urls"]),
                    ],
                    "current_evidence": list(hit_labels),
                    "status": "INVESTIGATION_CANDIDATE",
                    "requires_more_evidence": True,
                    "confidence": 0.35,
                    "equivalence_key": (
                        f"FEATURE_MAP:{surface['surface']}:"
                        f"{_equivalence_feature(feature_name)}"
                    ),
                    "generator": GENERATOR,
                    "surface": surface["surface"],
                    "feature": feature_name,
                    "reference": reference,
                    "reference_urls": list(feature["reference_urls"]),
                    "shared_flows": list(feature["shared_flows"]),
                    "matched_tokens": list(hit_tokens),
                    "advisory_only": True,
                    "human_approved_domain_checklist": True,
                }
            )
    return candidates


def is_present(map_path: str | Path | None = None) -> bool:
    """Return whether a usable, human-approved map is installed."""
    return bool(load_map(map_path)["surfaces"])


def summarize(
    evidence_pairs: object | None = None,
    map_path: str | Path | None = None,
) -> str:
    feature_map = load_map(map_path)
    surface_count = len(feature_map["surfaces"])
    feature_count = sum(len(surface["native_features"]) for surface in feature_map["surfaces"])
    if evidence_pairs is None:
        return f"AEM feature map: {surface_count} surface(s), {feature_count} approved feature(s)"
    candidates = candidates_for(evidence_pairs, map_path)
    matched_surfaces = {candidate["surface"] for candidate in candidates}
    return (
        f"AEM feature map: {len(candidates)} candidate(s) from "
        f"{len(matched_surfaces)} matched surface(s)"
    )


def _read_evidence_json(path: Path | None) -> object:
    if path is None:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, dict) and "evidence_pairs" in raw:
        return raw["evidence_pairs"]
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Curated AEM/Guides feature-map discovery")
    parser.add_argument("--map", type=Path, default=None)
    parser.add_argument("--evidence-json", type=Path, default=None)
    parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        metavar="LABEL=TEXT",
        help="add an evidence pair; may be repeated",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    pairs = _normalise_pairs(_read_evidence_json(args.evidence_json))
    for index, item in enumerate(args.evidence, start=1):
        label, separator, body = item.partition("=")
        if separator and body.strip():
            pairs.append((label.strip() or f"cli-{index}", body.strip()))
    candidates = candidates_for(pairs, args.map) if pairs else []
    if args.json:
        print(
            json.dumps(
                {
                    "summary": summarize(pairs if pairs else None, args.map),
                    "candidates": candidates,
                },
                indent=2,
            )
        )
    else:
        print(summarize(pairs if pairs else None, args.map))
        for problem in validate_repository_map(args.map):
            print(f"REVIEW feature-map: {problem}")
        for candidate in candidates:
            print(
                f"INVESTIGATION_CANDIDATE {candidate['surface']} / "
                f"{candidate['feature']}: {candidate['candidate']} "
                f"[{candidate['reference']}]"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
