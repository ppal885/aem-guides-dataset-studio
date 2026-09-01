#!/usr/bin/env python3
"""Recover a sealed, Jira-level Benchmark V2 from the authoritative UAC audit.

The builder verifies source provenance, forces implementation-exposed records
into TRAIN, creates deterministic disjoint splits, separates public generation
inputs from ignored private ground truth, and mines implementation-facing
reasoning artifacts from TRAIN only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from scan_benchmark_integrity import (
    TEXT_BASENAMES,
    TEXT_SUFFIXES,
    git_tracked_files,
    normalize_text,
    scan_records,
)


BENCHMARK_VERSION = "V2"
SCHEMA_VERSION = "aem-guides-human-uac-benchmark-v2"
DEFAULT_SEED = "aem-guides-uac-benchmark-v2-20260822"
EXPECTED_AUDIT_SCRIPT_SHA256 = "50def4cc9e491dd64963d23acfbd64a7d486de8f7deabebc4de7acdecd39422b"
EXPECTED_RECOVERED_INPUT_SHA256 = {
    "dataset_audit.json": "043744f20f89c50c658212ec44af990f6729c404034a6f2ff7b34c24c213d5d6",
    "authoritative_uac_dataset.jsonl": "8b5f8575bc48dd2eabff5a2006d5e90230eca453fd52eb1770f513bace7d22dd",
    "atomic_uac_requirements.jsonl": "f579209e3df7ffdc4ce78c6c1f2e5cdde16940eb89bfcd0331bba3b0142ff08c",
    "requirement_origin_analysis.jsonl": "07111cda306bc43385872f2b74f1053e3dc8a9eccbef5474dc6da8878ee0d8bf",
    "gap_classification.jsonl": "603e42615af9feaa171bbfac93c74eaccda3d701e3987fb4c2c5959ed426151b",
    "benchmark_split.json": "0daef8295413185fca6c83f66081c77604e725950080d9b9287e4518e72b20c6",
}
OUTCOME_LABEL_RE = re.compile(r"(?i)(?:^|[_-])uac(?:[_-]|$)|accepted|rejected|resolved|fixed")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(fieldnames or (list(rows[0]) if rows else []))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if columns:
            writer.writeheader()
            writer.writerows(rows)


def safe_labels(values: Sequence[Any]) -> list[str]:
    return sorted(
        {
            str(value).strip()
            for value in values
            if str(value).strip() and not OUTCOME_LABEL_RE.search(str(value).strip())
        }
    )


def primary_component(record: dict[str, Any]) -> str:
    values = record.get("components") or record.get("raw_components") or []
    return str(values[0]).strip() if values else "Unclassified"


def public_text(record: dict[str, Any]) -> str:
    pre = record.get("pre_uac_evidence") or {}
    values: list[str] = [str(record.get("summary") or "")]
    if isinstance(pre, dict):
        values.extend(str(pre.get(field) or "") for field in ("summary", "description"))
        comments = pre.get("comments") or []
        for comment in comments:
            if isinstance(comment, dict):
                values.append(str(comment.get("body") or comment.get("text") or ""))
            else:
                values.append(str(comment))
    return "\n".join(values)


def feature_archetypes(record: dict[str, Any]) -> list[str]:
    text = public_text(record)
    rules = [
        ("DITA_SEMANTIC", r"(?i)\b(?:dita|topicref|keyref|conref|xref|ditaval|bookmap|reltable|cals)\b"),
        ("UI_AUTHORING", r"(?i)\b(?:editor|author view|preview|dialog|panel|toolbar|cursor|scroll|viewport)\b"),
        ("PUBLISHING", r"(?i)\b(?:publish|output|native pdf|dita-ot|html5|aem site|preset)\b"),
        ("CONFIGURATION", r"(?i)\b(?:config|configuration|folder profile|feature flag|preference|default)\b"),
        ("BACKEND_API", r"(?i)\b(?:api|endpoint|servlet|service|request|response|payload|repository)\b"),
        ("STATE_LIFECYCLE", r"(?i)\b(?:create|save|reopen|refresh|copy|move|rename|delete|restore|upgrade|migrate)\b"),
    ]
    matched = [name for name, pattern in rules if re.search(pattern, text)]
    return matched or ["GENERAL"]


def complexity_band(requirements: Sequence[dict[str, Any]], patterns: Sequence[str]) -> str:
    score = len(requirements) + 2 * len(set(patterns))
    if score >= 25:
        return "high"
    if score >= 10:
        return "medium"
    return "low"


def requirement_count_band(count: int) -> str:
    if count >= 8:
        return "8_plus"
    if count >= 4:
        return "4_to_7"
    return "1_to_3"


def stratum_for(
    record: dict[str, Any],
    requirements: Sequence[dict[str, Any]],
    patterns: Sequence[str],
) -> tuple[str, str, str, str, str]:
    return (
        primary_component(record),
        str(record.get("issue_type") or "Unknown"),
        feature_archetypes(record)[0],
        complexity_band(requirements, patterns),
        requirement_count_band(len(requirements)),
    )


def build_duplicate_families(
    records: Sequence[dict[str, Any]],
    requirements_by_jira: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Group Jira whose answer evidence is exact or near-duplicate.

    This runs inside the sealed builder and emits identifiers/fingerprints only.
    No ground-truth text is written to manifests or reports.
    """

    keys = sorted(record["jira_key"] for record in records)
    parent = {key: key for key in keys}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    source_owners: dict[str, set[str]] = defaultdict(set)
    atomic_owners: dict[str, set[str]] = defaultdict(set)
    requirement_rows: list[dict[str, str]] = []
    for record in records:
        key = record["jira_key"]
        for source in record.get("authoritative_uac") or []:
            fingerprint = str(source.get("text_hash") or "").strip()
            if fingerprint:
                source_owners[fingerprint].add(key)
        for requirement in requirements_by_jira[key]:
            requirement_id = str(requirement.get("atomic_requirement_id") or "")
            for field in ("behavior", "original_text"):
                normalized = normalize_text(str(requirement.get(field) or ""))
                if not normalized:
                    continue
                fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                atomic_owners[fingerprint].add(key)
                if len(normalized) < 80 or len(normalized.split()) < 12:
                    continue
                requirement_rows.append(
                    {
                        "jira_key": key,
                        "requirement_id": requirement_id,
                        "normalized": normalized,
                        "fingerprint": fingerprint,
                    }
                )

    for owners in list(source_owners.values()) + list(atomic_owners.values()):
        ordered = sorted(owners)
        for other in ordered[1:]:
            union(ordered[0], other)

    shingle_sets: list[set[str]] = []
    shingle_frequency: Counter[str] = Counter()
    for row in requirement_rows:
        tokens = row["normalized"].split()
        shingles = {" ".join(tokens[index : index + 8]) for index in range(len(tokens) - 7)}
        shingle_sets.append(shingles)
        shingle_frequency.update(shingles)
    shingle_index: dict[str, list[int]] = defaultdict(list)
    for row_index, shingles in enumerate(shingle_sets):
        for shingle in sorted(shingles, key=lambda value: (shingle_frequency[value], value))[:4]:
            shingle_index[shingle].append(row_index)

    candidate_pairs: set[tuple[int, int]] = set()
    for indexes in shingle_index.values():
        for offset, left in enumerate(indexes):
            for right in indexes[offset + 1 :]:
                if requirement_rows[left]["jira_key"] == requirement_rows[right]["jira_key"]:
                    continue
                candidate_pairs.add((min(left, right), max(left, right)))
    near_duplicate_pairs: list[dict[str, Any]] = []
    for left_index, right_index in sorted(candidate_pairs):
        left = requirement_rows[left_index]
        right = requirement_rows[right_index]
        if left["fingerprint"] == right["fingerprint"]:
            continue
        similarity = SequenceMatcher(None, left["normalized"], right["normalized"]).ratio()
        if similarity < 0.92:
            continue
        union(left["jira_key"], right["jira_key"])
        near_duplicate_pairs.append(
            {
                "left_jira": left["jira_key"],
                "right_jira": right["jira_key"],
                "left_requirement_id": left["requirement_id"],
                "right_requirement_id": right["requirement_id"],
                "left_fingerprint": left["fingerprint"],
                "right_fingerprint": right["fingerprint"],
                "similarity": round(similarity, 6),
            }
        )

    grouped: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        grouped[find(key)].append(key)
    families = sorted((sorted(values) for values in grouped.values()), key=lambda values: values[0])
    family_rows = [
        {
            "family_id": f"DUP-{index:04d}",
            "jira_keys": family,
            "jira_count": len(family),
        }
        for index, family in enumerate(families, start=1)
    ]
    family_id_by_key = {
        key: row["family_id"] for row in family_rows for key in row["jira_keys"]
    }
    return {
        "families": family_rows,
        "family_id_by_key": family_id_by_key,
        "exact_source_fingerprint_count": len(source_owners),
        "shared_exact_source_fingerprint_count": sum(
            1 for owners in source_owners.values() if len(owners) > 1
        ),
        "exact_atomic_fingerprint_count": len(atomic_owners),
        "shared_exact_atomic_fingerprint_count": sum(
            1 for owners in atomic_owners.values() if len(owners) > 1
        ),
        "near_duplicate_pair_count": len(near_duplicate_pairs),
        "near_duplicate_pairs": near_duplicate_pairs,
        "multi_record_family_count": sum(1 for family in families if len(family) > 1),
        "max_family_size": max(map(len, families), default=0),
    }


def deterministic_split(
    records: Sequence[dict[str, Any]],
    requirements_by_jira: dict[str, list[dict[str, Any]]],
    patterns_by_jira: dict[str, list[str]],
    forced_train: set[str],
    duplicate_families: Sequence[Sequence[str]],
    *,
    seed: str,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    total = len(records)
    train_target = max(int(round(total * 0.60)), len(forced_train))
    holdout_total = total - train_target
    validation_target = int(round(holdout_total / 2))
    targets = {
        "train": train_target,
        "validation": validation_target,
        "blind": holdout_total - validation_target,
    }

    strata: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    stratum_by_key: dict[str, tuple[str, str, str, str, str]] = {}
    for record in records:
        key = record["jira_key"]
        stratum = stratum_for(record, requirements_by_jira[key], patterns_by_jira.get(key, []))
        strata[stratum].append(record)
        stratum_by_key[key] = stratum

    assignments: dict[str, str] = {}
    global_counts: Counter[str] = Counter()
    local_counts: dict[tuple[str, str, str, str, str], Counter[str]] = defaultdict(Counter)

    ratios = {name: target / total for name, target in targets.items()}
    family_by_key = {key: family for family in duplicate_families for key in family}
    forced_families = {
        tuple(family_by_key[key]) for key in forced_train if key in family_by_key
    }

    def assign_family(family: Sequence[str], split: str) -> None:
        for key in family:
            assignments[key] = split
            global_counts[split] += 1
            local_counts[stratum_by_key[key]][split] += 1

    for family in sorted(forced_families):
        assign_family(family, "train")
    if global_counts["train"] > targets["train"]:
        raise RuntimeError(
            f"{global_counts['train']} exposed/duplicate-family records exceed TRAIN capacity "
            f"{targets['train']}"
        )

    remaining_families = [
        list(family)
        for family in duplicate_families
        if not any(key in assignments for key in family)
    ]
    multi_families = [family for family in remaining_families if len(family) > 1]
    single_families = [family for family in remaining_families if len(family) == 1]

    def family_digest(family: Sequence[str]) -> str:
        return hashlib.sha256(f"{seed}|{'|'.join(sorted(family))}".encode("utf-8")).hexdigest()

    def choose_split(family: Sequence[str]) -> str:
        size = len(family)
        available = [
            name for name, target in targets.items() if global_counts[name] + size <= target
        ]
        if not available:
            raise RuntimeError(f"No partition has capacity for duplicate family: {sorted(family)}")

        def score(name: str) -> tuple[float, str]:
            local_pressure = 0.0
            for key in family:
                stratum = stratum_by_key[key]
                local_pressure += (local_counts[stratum][name] + 1) / max(
                    ratios[name] * len(strata[stratum]), 0.25
                )
            return (
                (global_counts[name] + size) / max(targets[name], 1)
                + 0.35 * local_pressure / size,
                name,
            )

        return min(available, key=score)

    for family in sorted(multi_families, key=lambda values: (-len(values), family_digest(values))):
        assign_family(family, choose_split(family))
    for family in sorted(single_families, key=family_digest):
        assign_family(family, choose_split(family))

    if dict(global_counts) != targets:
        raise RuntimeError(f"Split counts differ from deterministic targets: {dict(global_counts)}")

    for family in duplicate_families:
        family_splits = {assignments[key] for key in family}
        if len(family_splits) != 1:
            raise RuntimeError(f"Duplicate family crossed partitions: {sorted(family)}")

    rows: list[dict[str, Any]] = []
    for stratum, items in sorted(strata.items()):
        counts = local_counts[stratum]
        rows.append(
            {
                "component": stratum[0],
                "issue_type": stratum[1],
                "primary_archetype": stratum[2],
                "complexity": stratum[3],
                "requirement_count_band": stratum[4],
                "jira_count": len(items),
                "train": counts["train"],
                "validation": counts["validation"],
                "blind": counts["blind"],
            }
        )
    return assignments, rows


def public_record(record: dict[str, Any], source_csv_hash: str) -> dict[str, Any]:
    pre = dict(record.get("pre_uac_evidence") or {})
    pre["labels"] = safe_labels(pre.get("labels") or record.get("labels") or [])
    return {
        "schema_version": "aem-guides-pre-uac-public-input-v2",
        "benchmark_version": BENCHMARK_VERSION,
        "record_id": record["jira_key"],
        "jira_key": record["jira_key"],
        "summary": record.get("summary") or pre.get("summary") or "",
        "issue_type": record.get("issue_type") or "",
        "priority": record.get("priority") or "",
        "components": record.get("components") or record.get("raw_components") or [],
        "primary_component": primary_component(record),
        "created": record.get("created") or "",
        "pre_uac_evidence": pre,
        "source_snapshot": {
            "source_csv_sha256": source_csv_hash,
            "normalized_record_sha256": canonical_hash(record),
        },
    }


def assert_public_is_sealed(public: dict[str, Any], record: dict[str, Any]) -> None:
    serialized = json.dumps(public, ensure_ascii=False)
    forbidden_names = (
        "human_uac",
        "authoritative_uac",
        "post_uac_evidence",
        "acceptance_criteria",
        "ground_truth",
        "uac_workflow_status",
    )
    lowered = serialized.casefold()
    for name in forbidden_names:
        if name in lowered:
            raise RuntimeError(f"Public input {record['jira_key']} contains forbidden field marker {name}")
    normalized_public = normalize_text(serialized)
    for source in record.get("authoritative_uac") or []:
        source_text = str(source.get("text") or "")
        normalized_source = normalize_text(source_text)
        if len(normalized_source) >= 80 and len(normalized_source.split()) >= 12:
            if normalized_source in normalized_public:
                raise RuntimeError(f"Public input {record['jira_key']} contains authoritative UAC text")


def private_record(
    record: dict[str, Any],
    requirements: Sequence[dict[str, Any]],
    origins_by_requirement: dict[str, dict[str, Any]],
    gaps_by_requirement: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "aem-guides-human-uac-ground-truth-v2",
        "benchmark_version": BENCHMARK_VERSION,
        "record_id": record["jira_key"],
        "jira_key": record["jira_key"],
        "authoritative_uac": record.get("authoritative_uac") or [],
        "atomic_requirements": list(requirements),
        "requirement_origins": [
            origins_by_requirement[item["atomic_requirement_id"]]
            for item in requirements
            if item["atomic_requirement_id"] in origins_by_requirement
        ],
        "gap_classifications": [
            gaps_by_requirement[item["atomic_requirement_id"]]
            for item in requirements
            if item["atomic_requirement_id"] in gaps_by_requirement
        ],
        "source_record_sha256": canonical_hash(record),
    }


def skill_support(repo_root: Path, pattern_id: str) -> tuple[str, list[str]]:
    mapping = {
        "STATE": ["behavior_model.py", "state_compatibility_explorer.py"],
        "CONSUMER": ["coverage_hypotheses.py", "cross_surface_resolver.py"],
        "NFR": ["performance_contract.py"],
        "CONFIGURATION": ["affected_surface_explorer.py", "coverage_hypotheses.py"],
        "CHANGE": ["change_impact_explorer.py"],
        "CAPABILITY": ["capability_eligibility_explorer.py"],
        "SCOPE": ["scope_conflict_resolver.py"],
        "ORACLE": ["test_oracle_builder.py"],
        "DITA": ["semantic_relationship_explorer.py"],
    }
    candidates: list[str] = []
    for signal, filenames in mapping.items():
        if signal in pattern_id:
            candidates.extend(filenames)
    scripts_root = repo_root / "skills" / "test-plan-generation" / "scripts"
    found = sorted(
        {
            path.relative_to(repo_root).as_posix()
            for name in candidates
            for path in [scripts_root / name]
            if path.exists()
        }
    )
    if found:
        return "IMPLEMENTED_OR_ROUTED", found
    corpus = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (repo_root / "skills" / "test-plan-generation").rglob("*.py")
    )
    if pattern_id in corpus:
        return "IMPLEMENTED_OR_ROUTED", []
    return "NEEDS_REVIEW", []


def build_train_mining(
    repo_root: Path,
    train_root: Path,
    train_keys: set[str],
    records_by_key: dict[str, dict[str, Any]],
    requirements_by_jira: dict[str, list[dict[str, Any]]],
    gaps_by_requirement: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if set(records_by_key) != train_keys or set(requirements_by_jira) != train_keys:
        raise RuntimeError("TRAIN miner received a non-TRAIN record dictionary")
    train_requirement_ids = {
        requirement["atomic_requirement_id"]
        for requirements in requirements_by_jira.values()
        for requirement in requirements
    }
    if set(gaps_by_requirement) - train_requirement_ids:
        raise RuntimeError("TRAIN miner received non-TRAIN gap classifications")
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"jiras": set(), "requirements": [], "components": Counter()}
    )
    jira_rows: list[dict[str, Any]] = []
    for jira_key in sorted(train_keys):
        pattern_ids: set[str] = set()
        for requirement in requirements_by_jira[jira_key]:
            gap = gaps_by_requirement.get(requirement["atomic_requirement_id"]) or {}
            for pattern_id in gap.get("reasoning_dimensions") or []:
                pattern_ids.add(pattern_id)
                stats[pattern_id]["jiras"].add(jira_key)
                stats[pattern_id]["requirements"].append(requirement["atomic_requirement_id"])
                stats[pattern_id]["components"][primary_component(records_by_key[jira_key])] += 1
        jira_rows.append(
            {
                "jira_key": jira_key,
                "primary_component": primary_component(records_by_key[jira_key]),
                "archetypes": "|".join(feature_archetypes(records_by_key[jira_key])),
                "atomic_requirement_count": len(requirements_by_jira[jira_key]),
                "pattern_count": len(pattern_ids),
                "patterns": "|".join(sorted(pattern_ids)),
            }
        )

    patterns: list[dict[str, Any]] = []
    for pattern_id, item in stats.items():
        if len(item["jiras"]) < 2:
            continue
        phrase = re.sub(r"[_-]+", " ", pattern_id).strip().casefold()
        display_name = " ".join(word.upper() if len(word) <= 3 else word.title() for word in phrase.split())
        activation_signals = [
            f"Current issue evidence contains a requirement that needs {phrase}.",
            f"A testable outcome depends on resolving the {phrase} boundary.",
        ]
        negative_activation = [
            f"Do not activate from a Jira key, customer, or component match without current-issue {phrase} evidence.",
            "Do not reuse a ticket-specific expected output as a generic rule.",
        ]
        reasoning_questions = [
            f"What {phrase} decision is required to make the outcome observable and testable?",
            f"Which current-issue evidence confirms or constrains {phrase}?",
        ]
        evidence_to_seek = [
            "Current Jira/UAC or supplied incident acceptance contract.",
            "Inspected implementation, documentation, design, or automation evidence when applicable.",
        ]
        support_status, support_files = skill_support(repo_root, pattern_id)
        patterns.append(
            {
                "pattern_id": pattern_id,
                "name": display_name,
                "description": (
                    f"Apply {phrase} only when current issue evidence requires it; keep unresolved "
                    "decisions visible instead of importing a historical ticket answer."
                ),
                "activation_signals": activation_signals,
                "negative_activation": negative_activation,
                "reasoning_questions": reasoning_questions,
                "evidence_to_seek": evidence_to_seek,
                "possible_outputs": ["Acceptance criterion", "Test scenario", "Open question"],
                "cost_budget": 1,
                "priority": "P1",
                "definition_derivation": "DETERMINISTIC_FROM_TRAIN_OBSERVED_PATTERN_ID",
                "train_jira_count": len(item["jiras"]),
                "train_atomic_requirement_count": len(item["requirements"]),
                "source_jiras": sorted(item["jiras"]),
                "atomic_requirement_ids": sorted(set(item["requirements"])),
                "top_components": dict(item["components"].most_common()),
                "support_status": support_status,
                "support_files": support_files,
                "promotion_status": "PROMOTED_TRAIN_V2",
                "generalizability_test": (
                    "Apply the reasoning operation to an unseen Jira with different entity names; "
                    "activation must depend on behavioral signals, not a known Jira noun."
                ),
            }
        )
    patterns.sort(key=lambda item: (-item["train_jira_count"], item["pattern_id"]))
    taxonomy = {
        "schema_version": "aem-guides-qe-pattern-taxonomy-train-v2",
        "benchmark_version": BENCHMARK_VERSION,
        "derivation_partition": "TRAIN_V2_ONLY",
        "train_jira_count": len(train_keys),
        "pattern_count": len(patterns),
        "promotion_rule": "At least two distinct TRAIN V2 Jira keys",
        "definition_derivation": "Deterministic templates applied only to reasoning-dimension IDs observed in TRAIN V2",
        "historical_candidate_definitions_imported": False,
        "validation_ground_truth_used_for_pattern_discovery": False,
        "blind_ground_truth_used_for_pattern_discovery": False,
        "raw_human_uac_included": False,
        "patterns": patterns,
    }
    write_json(train_root / "reasoning_pattern_taxonomy_train_v2.json", taxonomy)

    yaml_rows = []
    for item in patterns:
        yaml_rows.append(
            {
                key: item[key]
                for key in (
                    "pattern_id",
                    "name",
                    "description",
                    "activation_signals",
                    "negative_activation",
                    "reasoning_questions",
                    "evidence_to_seek",
                    "possible_outputs",
                    "cost_budget",
                    "priority",
                    "train_jira_count",
                    "source_jiras",
                    "support_status",
                    "support_files",
                    "generalizability_test",
                )
            }
        )
    (train_root / "qe_reasoning_patterns_train_v2.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "aem-guides-qe-pattern-library-train-v2",
                "derivation_partition": "TRAIN_V2_ONLY",
                "patterns": yaml_rows,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    write_csv(train_root / "jira_pattern_matrix_train_v2.csv", jira_rows)

    component_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"jiras": set(), "requirements": 0}
    )
    for item in patterns:
        for jira_key in item["source_jiras"]:
            component = primary_component(records_by_key[jira_key])
            component_stats[(component, item["pattern_id"])]["jiras"].add(jira_key)
        for requirement_id in item["atomic_requirement_ids"]:
            jira_key = requirement_id.split(":REQ-", 1)[0]
            component = primary_component(records_by_key[jira_key])
            component_stats[(component, item["pattern_id"])]["requirements"] += 1
    component_rows = [
        {
            "component": component,
            "pattern_id": pattern_id,
            "train_jira_count": len(values["jiras"]),
            "train_atomic_requirement_count": values["requirements"],
        }
        for (component, pattern_id), values in sorted(component_stats.items())
    ]
    write_csv(train_root / "component_pattern_matrix_train_v2.csv", component_rows)

    trace_rows = [
        {
            "pattern_id": item["pattern_id"],
            "train_jira_count": item["train_jira_count"],
            "train_jira_keys": "|".join(item["source_jiras"]),
            "atomic_requirement_ids": "|".join(item["atomic_requirement_ids"]),
            "partition": "TRAIN_V2_ONLY",
        }
        for item in patterns
    ]
    write_csv(train_root / "pattern_traceability_train_v2.csv", trace_rows)

    missing_question_rows = [
        {
            "pattern_id": item["pattern_id"],
            "activation_signals": item["activation_signals"],
            "questions": item["reasoning_questions"],
            "evidence_to_seek": item["evidence_to_seek"],
            "if_unresolved": "OPEN_QUESTION",
            "source_jiras": item["source_jiras"],
        }
        for item in patterns
        if item["reasoning_questions"]
    ]
    (train_root / "missing_question_patterns_train_v2.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "aem-guides-missing-question-patterns-train-v2",
                "derivation_partition": "TRAIN_V2_ONLY",
                "patterns": missing_question_rows,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    gap_lines = [
        "# TRAIN V2 Skill Gap Analysis",
        "",
        "- Derivation boundary: TRAIN V2 only.",
        f"- TRAIN Jira: {len(train_keys)}.",
        f"- Promoted reusable patterns: {len(patterns)}.",
        "- Raw Human-UAC text is not included in this implementation-facing artifact.",
        "",
        "## Gaps",
        "",
    ]
    needs_review = [item for item in patterns if item["support_status"] == "NEEDS_REVIEW"]
    if needs_review:
        gap_lines.extend(
            f"- `{item['pattern_id']}`: {item['train_jira_count']} TRAIN Jira; current routing/support requires review."
            for item in needs_review
        )
    else:
        gap_lines.append("- No promoted TRAIN pattern is wholly unmapped by the current skill inventory.")
    (train_root / "skill_gap_analysis_train_v2.md").write_text("\n".join(gap_lines) + "\n", encoding="utf-8")

    priority_lines = [
        "# TRAIN V2 Implementation Priority",
        "",
        "- This ranking is derived from TRAIN V2 only.",
        "- It is evidence for later implementation planning, not authorization to change production in Phase 0A.",
        "",
    ]
    for rank, item in enumerate(patterns, start=1):
        priority_lines.append(
            f"- P{1 if rank <= 12 else 2} `{item['pattern_id']}` - {item['train_jira_count']} TRAIN Jira; "
            f"support `{item['support_status']}`; traceability in `pattern_traceability_train_v2.csv`."
        )
    (train_root / "implementation_priority_train_v2.md").write_text(
        "\n".join(priority_lines) + "\n", encoding="utf-8"
    )
    return taxonomy


def _tracked_plus_generated(repo_root: Path, generated: Path) -> list[Path]:
    files = git_tracked_files(repo_root)
    files.extend(path for path in generated.rglob("*") if path.is_file())
    return [
        path
        for path in files
        if (path.suffix.casefold() in TEXT_SUFFIXES or path.name.casefold() in TEXT_BASENAMES)
        and "benchmark/v2/private" not in path.as_posix()
        and "benchmark/v2/public" not in path.as_posix()
        and "benchmark/v2/manifests" not in path.as_posix()
        and "benchmark/v2/reports" not in path.as_posix()
    ]


def build(repo_root: Path, audit_dir: Path, seed: str) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    audit_dir = audit_dir.resolve()
    benchmark_root = repo_root / "benchmark" / "v2"
    public_root = benchmark_root / "public"
    private_root = benchmark_root / "private"
    manifest_root = benchmark_root / "manifests"
    reports_root = benchmark_root / "reports"
    train_root = benchmark_root / "train_mining"
    for path in (public_root, private_root, manifest_root, reports_root, train_root):
        path.mkdir(parents=True, exist_ok=True)
    stale_invalidation_report = reports_root / "corpus_invalidation.json"
    if stale_invalidation_report.exists():
        stale_invalidation_report.unlink()

    audit_path = audit_dir / "dataset_audit.json"
    for filename, expected_hash in EXPECTED_RECOVERED_INPUT_SHA256.items():
        recovered_path = audit_dir / filename
        if not recovered_path.is_file() or sha256_file(recovered_path) != expected_hash:
            raise RuntimeError(f"Recovered audit input checksum mismatch: {filename}")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    source_csv = Path(audit["csv"]["path"])
    if not source_csv.exists():
        raise RuntimeError(f"AUTHORITATIVE_DATASET_REQUIRED: missing {source_csv}")
    if sha256_file(source_csv) != audit["csv"]["sha256"]:
        raise RuntimeError("Authoritative CSV checksum does not match dataset_audit.json")
    audit_script = audit_dir / "run_human_uac_reasoning_mining.py"
    if sha256_file(audit_script) != EXPECTED_AUDIT_SCRIPT_SHA256:
        raise RuntimeError("Recovered mining script checksum differs from the audited version")

    records = load_jsonl(audit_dir / "authoritative_uac_dataset.jsonl")
    requirements = load_jsonl(audit_dir / "atomic_uac_requirements.jsonl")
    origins = load_jsonl(audit_dir / "requirement_origin_analysis.jsonl")
    gaps = load_jsonl(audit_dir / "gap_classification.jsonl")
    original_split = json.loads((audit_dir / "benchmark_split.json").read_text(encoding="utf-8"))

    records_by_key = {record["jira_key"]: record for record in records}
    if len(records_by_key) != len(records):
        raise RuntimeError("Authoritative normalized dataset has duplicate Jira keys")
    requirements_by_jira: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for requirement in requirements:
        requirements_by_jira[requirement["jira_key"]].append(requirement)
    origins_by_requirement = {item["atomic_requirement_id"]: item for item in origins}
    gaps_by_requirement = {item["atomic_requirement_id"]: item for item in gaps}
    patterns_by_jira: dict[str, list[str]] = defaultdict(list)
    for requirement in requirements:
        gap = gaps_by_requirement.get(requirement["atomic_requirement_id"]) or {}
        patterns_by_jira[requirement["jira_key"]].extend(gap.get("reasoning_dimensions") or [])
    patterns_by_jira = {key: sorted(set(value)) for key, value in patterns_by_jira.items()}

    authoritative = [record for record in records if record.get("authoritative_uac")]
    eligible = [record for record in authoritative if requirements_by_jira.get(record["jira_key"])]
    unsuitable = [record for record in authoritative if not requirements_by_jira.get(record["jira_key"])]
    if (len(authoritative), len(eligible), len(unsuitable)) != (269, 264, 5):
        raise RuntimeError(
            f"Recovered universe differs from audited 269/264/5: "
            f"{len(authoritative)}/{len(eligible)}/{len(unsuitable)}"
        )

    scan_source_records = [
        private_record(
            record,
            requirements_by_jira[record["jira_key"]],
            origins_by_requirement,
            gaps_by_requirement,
        )
        for record in eligible
    ]
    pre_split_scan = scan_records(repo_root, scan_source_records)
    write_json(reports_root / "pre_split_exposure_scan.json", pre_split_scan)
    forced_train = set(pre_split_scan["exposed_record_identifiers"])
    baseline_metrics = repo_root / "analysis" / "baseline_metrics.json"
    if baseline_metrics.exists():
        baseline_key = json.loads(baseline_metrics.read_text(encoding="utf-8"))["runtime"]["train_case"]
        if baseline_key in requirements_by_jira:
            forced_train.add(baseline_key)

    duplicate_audit = build_duplicate_families(eligible, requirements_by_jira)
    duplicate_families = [row["jira_keys"] for row in duplicate_audit["families"]]
    family_by_key = {
        key: set(family) for family in duplicate_families for key in family
    }
    exposed_before_family_expansion = set(forced_train)
    forced_train = set().union(
        *(family_by_key[key] for key in exposed_before_family_expansion)
    ) if exposed_before_family_expansion else set()

    assignments, strata = deterministic_split(
        eligible,
        requirements_by_jira,
        patterns_by_jira,
        forced_train,
        duplicate_families,
        seed=seed,
    )
    split_keys = {
        split: sorted(key for key, assigned in assignments.items() if assigned == split)
        for split in ("train", "validation", "blind")
    }
    split_sets = {name: set(keys) for name, keys in split_keys.items()}
    overlaps = {
        "train_validation": sorted(split_sets["train"] & split_sets["validation"]),
        "train_blind": sorted(split_sets["train"] & split_sets["blind"]),
        "validation_blind": sorted(split_sets["validation"] & split_sets["blind"]),
    }
    if any(overlaps.values()) or len(set().union(*split_sets.values())) != len(eligible):
        raise RuntimeError("V2 split is not globally disjoint and complete")

    source_fingerprints: dict[str, set[str]] = defaultdict(set)
    atomic_fingerprints: dict[str, set[str]] = defaultdict(set)
    for split, keys in split_keys.items():
        for key in keys:
            record = records_by_key[key]
            source_fingerprints[split].update(
                str(source.get("text_hash") or "").strip()
                for source in record.get("authoritative_uac") or []
                if str(source.get("text_hash") or "").strip()
            )
            for requirement in requirements_by_jira[key]:
                for field in ("behavior", "original_text"):
                    normalized = normalize_text(str(requirement.get(field) or ""))
                    if normalized:
                        atomic_fingerprints[split].add(
                            hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                        )
    fingerprint_overlaps = {
        "source_train_validation": sorted(
            source_fingerprints["train"] & source_fingerprints["validation"]
        ),
        "source_train_blind": sorted(source_fingerprints["train"] & source_fingerprints["blind"]),
        "source_validation_blind": sorted(
            source_fingerprints["validation"] & source_fingerprints["blind"]
        ),
        "atomic_train_validation": sorted(
            atomic_fingerprints["train"] & atomic_fingerprints["validation"]
        ),
        "atomic_train_blind": sorted(atomic_fingerprints["train"] & atomic_fingerprints["blind"]),
        "atomic_validation_blind": sorted(
            atomic_fingerprints["validation"] & atomic_fingerprints["blind"]
        ),
    }
    near_duplicate_cross_partition = [
        pair
        for pair in duplicate_audit["near_duplicate_pairs"]
        if assignments[pair["left_jira"]] != assignments[pair["right_jira"]]
    ]
    if any(fingerprint_overlaps.values()) or near_duplicate_cross_partition:
        raise RuntimeError("Answer fingerprint or near-duplicate family crossed V2 partitions")

    write_json(
        manifest_root / "duplicate_families.json",
        {
            "schema_version": "aem-guides-benchmark-duplicate-families-v2",
            "matching_policy": {
                "exact_authoritative_source_hash": True,
                "exact_atomic_requirement_hash": True,
                "near_duplicate_threshold": 0.92,
                "near_duplicate_candidate_width_tokens": 8,
            },
            "family_count": len(duplicate_audit["families"]),
            "multi_record_family_count": duplicate_audit["multi_record_family_count"],
            "max_family_size": duplicate_audit["max_family_size"],
            "shared_exact_source_fingerprint_count": duplicate_audit[
                "shared_exact_source_fingerprint_count"
            ],
            "shared_exact_atomic_fingerprint_count": duplicate_audit[
                "shared_exact_atomic_fingerprint_count"
            ],
            "near_duplicate_pair_count": duplicate_audit["near_duplicate_pair_count"],
            "families": duplicate_audit["families"],
            "near_duplicate_pairs": duplicate_audit["near_duplicate_pairs"],
            "cross_partition_fingerprint_overlaps": fingerprint_overlaps,
            "cross_partition_near_duplicate_pairs": near_duplicate_cross_partition,
            "ground_truth_text_in_manifest": False,
        },
    )

    public_by_key: dict[str, dict[str, Any]] = {}
    private_by_key: dict[str, dict[str, Any]] = {}
    for record in eligible:
        key = record["jira_key"]
        public = public_record(record, audit["csv"]["sha256"])
        assert_public_is_sealed(public, record)
        public_by_key[key] = public
        private_by_key[key] = private_record(
            record,
            requirements_by_jira[key],
            origins_by_requirement,
            gaps_by_requirement,
        )
    for split, keys in split_keys.items():
        write_jsonl(public_root / f"{split}_inputs.jsonl", (public_by_key[key] for key in keys))
        write_jsonl(
            private_root / f"{split}_ground_truth.jsonl", (private_by_key[key] for key in keys)
        )

    unsuitable_payload = {
        "schema_version": SCHEMA_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "count": len(unsuitable),
        "records": [
            {
                "jira_key": record["jira_key"],
                "reason": "Authoritative source has no self-contained atomic behavior after deterministic extraction.",
                "source_record_sha256": canonical_hash(record),
                "authoritative_source_hashes": sorted(
                    source.get("text_hash") or "" for source in record.get("authoritative_uac") or []
                ),
            }
            for record in sorted(unsuitable, key=lambda item: item["jira_key"])
        ],
    }
    write_json(manifest_root / "unsuitable_records.json", unsuitable_payload)

    record_manifest_rows = []
    for record in sorted(authoritative, key=lambda item: item["jira_key"]):
        key = record["jira_key"]
        reqs = requirements_by_jira.get(key, [])
        record_manifest_rows.append(
            {
                "jira_key": key,
                "suitability": "ELIGIBLE" if reqs else "UNSUITABLE",
                "assigned_split": assignments.get(key),
                "primary_component": primary_component(record),
                "issue_type": record.get("issue_type") or "",
                "feature_archetypes": feature_archetypes(record),
                "requirement_count": len(reqs),
                "source_record_sha256": canonical_hash(record),
                "public_input_sha256": canonical_hash(public_by_key[key]) if key in public_by_key else None,
                "private_ground_truth_sha256": canonical_hash(private_by_key[key]) if key in private_by_key else None,
                "authoritative_source_hashes": sorted(
                    source.get("text_hash") or "" for source in record.get("authoritative_uac") or []
                ),
                "atomic_requirement_hashes": sorted(
                    hashlib.sha256(normalize_text(item.get("behavior") or "").encode("utf-8")).hexdigest()
                    for item in reqs
                ),
                "duplicate_family_id": duplicate_audit["family_id_by_key"].get(key),
                "implementation_exposed_before_split": key in exposed_before_family_expansion,
                "forced_to_train_by_duplicate_family": (
                    key in forced_train and key not in exposed_before_family_expansion
                ),
            }
        )
    write_json(
        manifest_root / "authoritative_records.json",
        {
            "schema_version": SCHEMA_VERSION,
            "benchmark_version": BENCHMARK_VERSION,
            "authoritative_record_count": len(authoritative),
            "records": record_manifest_rows,
        },
    )

    original_blind = set(original_split["jira_ids"]["blind_benchmark"])
    retired_original_blind = sorted(original_blind & forced_train)
    split_manifest = {
        "schema_version": SCHEMA_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "seed": seed,
        "strategy": (
            "Deterministic Jira-key-level stratification by component, issue type, primary feature "
            "archetype, complexity, and requirement-count band; exact-source, exact-atomic, and "
            "high-threshold near-duplicate families remain atomic; implementation-exposed families "
            "are forced to TRAIN."
        ),
        "target_ratio": {"train": 0.60, "validation": 0.20, "blind": 0.20},
        "target_policy": (
            "Use 60/20/20 when all exposed duplicate families fit within the 60% TRAIN target; "
            "otherwise expand TRAIN to contain every exposed family and divide the remaining "
            "holdout Jira as evenly as possible between VALIDATION and BLIND."
        ),
        "historical_158_53_53_target_possible": len(forced_train) <= 158,
        "counts": {name: len(keys) for name, keys in split_keys.items()},
        "actual_ratio": {
            name: round(len(keys) / len(eligible), 6) for name, keys in split_keys.items()
        },
        "unsuitable_count": len(unsuitable),
        "jira_ids": split_keys,
        "forced_train_record_identifiers": sorted(forced_train),
        "directly_exposed_record_identifiers": sorted(exposed_before_family_expansion),
        "duplicate_family_expansion_record_identifiers": sorted(
            forced_train - exposed_before_family_expansion
        ),
        "retired_original_blind_record_identifiers": retired_original_blind,
        "overlaps": overlaps,
        "answer_fingerprint_overlaps": fingerprint_overlaps,
        "near_duplicate_cross_partition_pairs": near_duplicate_cross_partition,
        "unsuitable_in_active_partitions": sorted(
            set(item["jira_key"] for item in unsuitable) & set().union(*split_sets.values())
        ),
        "strata": strata,
        "guards": [
            "All atomic requirements from one Jira remain in one partition.",
            "TRAIN, VALIDATION, and BLIND are globally Jira-key disjoint.",
            "Exact source, exact atomic-requirement, and detected 0.92 near-duplicate families never cross partitions.",
            "Implementation-exposed records are in TRAIN, never VALIDATION or BLIND.",
            "Public inputs contain only Pre-UAC evidence and no Human-UAC ground truth.",
            "Private ground truth is ignored by Git and unavailable to generation_access.py.",
        ],
    }
    write_json(manifest_root / "split_manifest.json", split_manifest)

    train_records_by_key = {key: records_by_key[key] for key in split_keys["train"]}
    train_requirements_by_jira = {
        key: requirements_by_jira[key] for key in split_keys["train"]
    }
    train_requirement_ids = {
        requirement["atomic_requirement_id"]
        for requirements in train_requirements_by_jira.values()
        for requirement in requirements
    }
    train_gaps_by_requirement = {
        requirement_id: gaps_by_requirement[requirement_id]
        for requirement_id in sorted(train_requirement_ids)
        if requirement_id in gaps_by_requirement
    }
    train_mining_input = {
        "schema_version": "aem-guides-train-mining-input-v2",
        "partition": "TRAIN_V2_ONLY",
        "jira_keys": split_keys["train"],
        "record_hashes": {
            key: canonical_hash(train_records_by_key[key]) for key in split_keys["train"]
        },
        "requirement_hashes": {
            requirement_id: canonical_hash(
                next(
                    requirement
                    for requirements in train_requirements_by_jira.values()
                    for requirement in requirements
                    if requirement["atomic_requirement_id"] == requirement_id
                )
            )
            for requirement_id in sorted(train_requirement_ids)
        },
        "gap_hashes": {
            requirement_id: canonical_hash(train_gaps_by_requirement[requirement_id])
            for requirement_id in sorted(train_gaps_by_requirement)
        },
        "validation_jira_count": 0,
        "blind_jira_count": 0,
        "ground_truth_text_in_manifest": False,
    }
    write_json(manifest_root / "train_mining_input.json", train_mining_input)

    taxonomy = build_train_mining(
        repo_root,
        train_root,
        split_sets["train"],
        train_records_by_key,
        train_requirements_by_jira,
        train_gaps_by_requirement,
    )

    blind_records = [private_by_key[key] for key in split_keys["blind"]]
    post_scan = scan_records(
        repo_root,
        blind_records,
        tracked_files=_tracked_plus_generated(repo_root, train_root),
    )
    write_json(reports_root / "content_leakage_scan.json", post_scan)
    if post_scan["summary"]["prohibited_contaminated_record_count"]:
        raise RuntimeError("Generated V2 BLIND partition still has implementation-facing contamination")

    split_integrity = "\n".join(
        [
            "# Benchmark V2 Split Integrity",
            "",
            f"- Version: `{BENCHMARK_VERSION}`.",
            f"- Seed: `{seed}`.",
            f"- Authoritative records: {len(authoritative)}.",
            f"- TRAIN: {len(split_keys['train'])}.",
            f"- VALIDATION: {len(split_keys['validation'])}.",
            f"- BLIND: {len(split_keys['blind'])}.",
            f"- Unsuitable: {len(unsuitable)}.",
            f"- Historical 158/53/53 target possible after exposure/family grouping: {len(forced_train) <= 158}.",
            "- Pairwise overlap: 0.",
            "- Cross-partition authoritative-source fingerprint overlap: 0.",
            "- Cross-partition atomic-requirement fingerprint overlap: 0.",
            "- Cross-partition detected high-threshold near-duplicate pairs: 0.",
            "- Unsuitable records in active partitions: 0.",
            f"- Directly exposed records: {len(exposed_before_family_expansion)}.",
            f"- Records forced to TRAIN after duplicate-family expansion: {len(forced_train)}.",
            f"- Original blind records retired from blind placement: {len(retired_original_blind)}.",
            "- Public/private field leakage checks: PASS.",
            "- Ground-truth content is not included in this report.",
        ]
    )
    (reports_root / "split_integrity.md").write_text(split_integrity + "\n", encoding="utf-8")
    contamination_report = "\n".join(
        [
            "# Benchmark V2 Contamination Audit",
            "",
            "- The historical 36-pattern taxonomy is classified `EXPLORATORY_FULL_CORPUS_ANALYSIS`.",
            "- It was not imported as implementation-facing V2 pattern evidence.",
            f"- Pre-split exposed record identifiers: {pre_split_scan['summary']['exposed_record_count']}.",
            f"- Pre-split prohibited contaminated identifiers: {pre_split_scan['summary']['prohibited_contaminated_record_count']}.",
            f"- V2 BLIND prohibited contamination after replacement: {post_scan['summary']['prohibited_contaminated_record_count']}.",
            "- Official product-documentation retrieval corpora were preserved byte-for-byte; eligible Jira identifiers they expose are assigned to TRAIN.",
            f"- TRAIN-only promoted patterns: {taxonomy['pattern_count']}.",
            "- Scanner output contains identifiers and hashes only; no Human-UAC text.",
        ]
    )
    (reports_root / "contamination_audit.md").write_text(contamination_report + "\n", encoding="utf-8")

    provenance = {
        "schema_version": SCHEMA_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "source_csv": {
            "path": str(source_csv),
            "bytes": source_csv.stat().st_size,
            "sha256": sha256_file(source_csv),
        },
        "recovered_audit": {
            "directory": str(audit_dir),
            "dataset_audit": {"path": str(audit_path), "sha256": sha256_file(audit_path)},
            "normalized_dataset": {
                "path": str(audit_dir / "authoritative_uac_dataset.jsonl"),
                "sha256": sha256_file(audit_dir / "authoritative_uac_dataset.jsonl"),
            },
            "atomic_requirements": {
                "path": str(audit_dir / "atomic_uac_requirements.jsonl"),
                "sha256": sha256_file(audit_dir / "atomic_uac_requirements.jsonl"),
            },
            "requirement_origins": {
                "path": str(audit_dir / "requirement_origin_analysis.jsonl"),
                "sha256": sha256_file(audit_dir / "requirement_origin_analysis.jsonl"),
            },
            "gap_classification": {
                "path": str(audit_dir / "gap_classification.jsonl"),
                "sha256": sha256_file(audit_dir / "gap_classification.jsonl"),
            },
            "historical_split": {
                "path": str(audit_dir / "benchmark_split.json"),
                "sha256": sha256_file(audit_dir / "benchmark_split.json"),
            },
            "mining_script": {"path": str(audit_script), "sha256": sha256_file(audit_script)},
        },
        "historical_pattern_artifact_classification": "EXPLORATORY_FULL_CORPUS_ANALYSIS",
        "historical_pattern_candidates_loaded_by_v2_builder": False,
        "v2_pattern_derivation": "TRAIN_V2_ONLY",
        "v2_pattern_definition_derivation": "DETERMINISTIC_FROM_TRAIN_OBSERVED_PATTERN_ID",
        "train_mining_input": {
            "path": "benchmark/v2/manifests/train_mining_input.json",
            "sha256": sha256_file(manifest_root / "train_mining_input.json"),
        },
        "validation_ground_truth_used_for_pattern_discovery": False,
        "blind_ground_truth_used_for_pattern_discovery": False,
        "builder": {
            "path": "scripts/build_benchmark_v2.py",
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "scanner": {
            "path": "scripts/scan_benchmark_integrity.py",
            "sha256": sha256_file(Path(__file__).with_name("scan_benchmark_integrity.py")),
        },
    }
    write_json(manifest_root / "provenance.json", provenance)

    checksum_rows: dict[str, dict[str, Any]] = {}
    for root in (public_root, private_root, manifest_root, reports_root, train_root):
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name == "checksums.json":
                continue
            relative = path.relative_to(repo_root).as_posix()
            checksum_rows[relative] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    write_json(
        manifest_root / "checksums.json",
        {
            "schema_version": "aem-guides-benchmark-checksums-v2",
            "benchmark_version": BENCHMARK_VERSION,
            "files": checksum_rows,
        },
    )
    return {
        "status": "PASS",
        "benchmark_version": BENCHMARK_VERSION,
        "authoritative_record_count": len(authoritative),
        "train_count": len(split_keys["train"]),
        "validation_count": len(split_keys["validation"]),
        "blind_count": len(split_keys["blind"]),
        "unsuitable_count": len(unsuitable),
        "overlap_count": sum(len(value) for value in overlaps.values()),
        "blind_contamination_count": post_scan["summary"]["prohibited_contaminated_record_count"],
        "train_only_pattern_count": taxonomy["pattern_count"],
        "forced_train_count": len(forced_train),
        "retired_original_blind_count": len(retired_original_blind),
        "benchmark_root": str(benchmark_root),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=Path(r"C:\Users\prashantp\Videos\aem-guides-uac-reasoning-audit\analysis"),
    )
    parser.add_argument("--seed", default=DEFAULT_SEED)
    args = parser.parse_args()
    result = build(args.repo_root, args.audit_dir, args.seed)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
