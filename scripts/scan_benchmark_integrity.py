#!/usr/bin/env python3
"""Sealed benchmark leakage scanner.

The scanner reads benchmark ground truth locally and emits identifiers, hashes,
locations, and classifications only. It never writes or prints Human-UAC text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Sequence


TEXT_SUFFIXES = {
    ".bat",
    ".c",
    ".cc",
    ".cfg",
    ".cmd",
    ".conf",
    ".cpp",
    ".cs",
    ".csv",
    ".feature",
    ".go",
    ".gradle",
    ".groovy",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".js",
    ".java",
    ".json",
    ".jsonl",
    ".kt",
    ".kts",
    ".md",
    ".php",
    ".properties",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".svelte",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_BASENAMES = {"dockerfile", "makefile", "procfile"}
ALLOWED_PREFIXES = (
    "benchmark/v2/public/",
    "benchmark/v2/manifests/",
    "benchmark/v2/reports/",
)
EXCLUDED_PREFIXES = (
    "benchmark/v2/private/",
    ".git/",
    ".claude/worktrees/",
    ".worktrees/",
    "backend/.venv/",
    "frontend/node_modules/",
)
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_./:-]*", re.IGNORECASE)
JIRA_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(TOKEN_RE.findall(normalized))


def text_fingerprint(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def git_tracked_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    files: list[Path] = []
    for raw in result.stdout.splitlines():
        rel = raw.replace("\\", "/")
        if rel.startswith(EXCLUDED_PREFIXES) or rel.startswith(ALLOWED_PREFIXES):
            continue
        path = repo_root / rel
        if path.is_file() and (
            path.suffix.casefold() in TEXT_SUFFIXES or path.name.casefold() in TEXT_BASENAMES
        ):
            files.append(path)
    return files


def classify_path(relative_path: str) -> str:
    value = relative_path.replace("\\", "/").casefold()
    if "/benchmarks/" in value and "manifest" in value:
        return "ALLOWED_SPLIT_MANIFEST"
    if "integrity" in value or "checksum" in value:
        return "ALLOWED_CHECKSUM_OR_INTEGRITY_REPORT"
    if "/tests/" in value or value.startswith("tests/"):
        return "PROHIBITED_TEST"
    if "fixture" in value:
        return "PROHIBITED_REGRESSION_FIXTURE"
    if "/output/" in value or value.startswith("output/"):
        return "PROHIBITED_EXPECTED_OUTPUT"
    if "/prompts/" in value or value.endswith("skill.md"):
        return "PROHIBITED_PROMPT"
    if "/config/" in value or "/storage/" in value:
        return "PROHIBITED_IMPLEMENTATION_GUIDANCE"
    if any(part in value for part in ("/skills/", "/references/", "/analysis/", "/docs/")):
        return "PROHIBITED_IMPLEMENTATION_GUIDANCE"
    if value.endswith((".py", ".ts", ".tsx", ".js")):
        return "PROHIBITED_IMPLEMENTATION_GUIDANCE"
    return "UNKNOWN"


def _is_prohibited(classification: str) -> bool:
    return not classification.startswith("ALLOWED_")


def _line_for_literal(text: str, literal: str) -> int:
    offset = text.find(literal)
    return text.count("\n", 0, max(offset, 0)) + 1 if offset >= 0 else 1


def _normalized_tokens_with_lines(text: str) -> tuple[list[str], list[int]]:
    tokens: list[str] = []
    lines: list[int] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        normalized_line = unicodedata.normalize("NFKC", raw_line).casefold()
        line_tokens = TOKEN_RE.findall(normalized_line)
        tokens.extend(line_tokens)
        lines.extend([line_number] * len(line_tokens))
    return tokens, lines


def _requirement_rows(records: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        jira_key = str(record.get("jira_key") or record.get("record_id") or "").strip()
        for source_index, source in enumerate(record.get("authoritative_uac") or [], start=1):
            if not isinstance(source, dict):
                continue
            raw = source.get("text") or source.get("value") or source.get("content")
            if not isinstance(raw, str):
                continue
            normalized = normalize_text(raw)
            if len(normalized) < 16 or len(normalized.split()) < 3:
                continue
            rows.append(
                {
                    "jira_key": jira_key,
                    "requirement_id": f"{jira_key}:SOURCE-{source_index:02d}",
                    "normalized": normalized,
                    "fingerprint": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                }
            )
        for requirement in record.get("atomic_requirements") or []:
            requirement_id = str(requirement.get("atomic_requirement_id") or "").strip()
            for field in ("behavior", "original_text"):
                raw = requirement.get(field)
                if not isinstance(raw, str):
                    continue
                normalized = normalize_text(raw)
                if len(normalized) < 16 or len(normalized.split()) < 3:
                    continue
                rows.append(
                    {
                        "jira_key": jira_key,
                        "requirement_id": requirement_id,
                        "normalized": normalized,
                        "fingerprint": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                    }
                )
    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        unique[(row["jira_key"], row["requirement_id"], row["fingerprint"])] = row
    return list(unique.values())


def _distinctive_shingles(rows: Sequence[dict[str, str]], width: int = 8) -> dict[str, list[int]]:
    row_shingles: list[set[str]] = []
    frequencies: Counter[str] = Counter()
    for row in rows:
        tokens = row["normalized"].split()
        shingles = (
            {" ".join(tokens[index : index + width]) for index in range(len(tokens) - width + 1)}
            if len(tokens) >= width and len(row["normalized"]) >= 80 and len(tokens) >= 12
            else set()
        )
        row_shingles.append(shingles)
        frequencies.update(shingles)
    index: dict[str, list[int]] = defaultdict(list)
    for row_index, shingles in enumerate(row_shingles):
        chosen = sorted(shingles, key=lambda value: (frequencies[value], -len(value), value))[:4]
        for shingle in chosen:
            index[shingle].append(row_index)
    return index


def scan_records(
    repo_root: Path,
    records: Sequence[dict[str, Any]],
    *,
    tracked_files: Sequence[Path] | None = None,
) -> dict[str, Any]:
    """Return a sealed leakage report without including matched source text."""

    repo_root = repo_root.resolve()
    files = list(tracked_files) if tracked_files is not None else git_tracked_files(repo_root)
    record_ids = {
        str(record.get("jira_key") or record.get("record_id") or "").strip()
        for record in records
        if str(record.get("jira_key") or record.get("record_id") or "").strip()
    }
    requirements = _requirement_rows(records)
    shingle_index = _distinctive_shingles(requirements)
    exact_anchor_index: dict[str, list[int]] = defaultdict(list)
    for requirement_index, row in enumerate(requirements):
        exact_anchor_index[" ".join(row["normalized"].split()[:3])].append(requirement_index)
    matches: dict[tuple[str, int, str, str, str], dict[str, Any]] = {}

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        relative = path.resolve().relative_to(repo_root).as_posix()
        classification = classify_path(relative)
        remediation = (
            "Move the record to TRAIN or remove and regenerate this artifact from TRAIN-only evidence."
            if _is_prohibited(classification)
            else "Reference may remain in a sealed benchmark manifest or integrity report."
        )

        for match in JIRA_RE.finditer(text):
            jira_key = match.group(0)
            if jira_key not in record_ids:
                continue
            line = text.count("\n", 0, match.start()) + 1
            key = (relative, line, jira_key, "", "JIRA_KEY")
            matches[key] = {
                "contaminated_file": relative,
                "location": f"{relative}:{line}",
                "matched_record_identifier": jira_key,
                "requirement_identifier": None,
                "match_category": "JIRA_KEY",
                "classification": classification,
                "similarity": 1.0,
                "fingerprint": hashlib.sha256(jira_key.encode("utf-8")).hexdigest(),
                "remediation_required": remediation,
                "prohibited": _is_prohibited(classification),
            }

        file_tokens, token_lines = _normalized_tokens_with_lines(text)
        normalized_file = " ".join(file_tokens)
        if len(normalized_file) < 16 or len(file_tokens) < 3:
            continue
        # Probe the file's shingles against the sealed index.  Iterating every
        # ground-truth shingle for every repository file is quadratic enough to
        # make a full-repository audit impractical.
        candidate_anchors: dict[int, set[str]] = defaultdict(set)
        candidate_lines: dict[int, set[int]] = defaultdict(set)
        exact_candidate_positions: dict[int, list[int]] = defaultdict(list)
        for token_index in range(max(0, len(file_tokens) - 3 + 1)):
            anchor = " ".join(file_tokens[token_index : token_index + 3])
            for requirement_index in exact_anchor_index.get(anchor, ()):
                exact_candidate_positions[requirement_index].append(token_index)
                candidate_lines[requirement_index].add(token_lines[token_index])
        for token_index in range(max(0, len(file_tokens) - 8 + 1)):
            shingle = " ".join(file_tokens[token_index : token_index + 8])
            for requirement_index in shingle_index.get(shingle, ()):
                candidate_anchors[requirement_index].add(shingle)
                candidate_lines[requirement_index].add(token_lines[token_index])
        candidate_indexes = set(candidate_anchors) | set(exact_candidate_positions)
        for index in sorted(candidate_indexes):
            row = requirements[index]
            normalized_requirement = row["normalized"]
            requirement_tokens = normalized_requirement.split()
            exact_position = next(
                (
                    position
                    for position in exact_candidate_positions.get(index, ())
                    if file_tokens[position : position + len(requirement_tokens)] == requirement_tokens
                ),
                None,
            )
            if exact_position is not None:
                category = "EXACT_REQUIREMENT_HASH"
                similarity = 1.0
                line = token_lines[exact_position]
            else:
                if index not in candidate_anchors:
                    continue
                anchor = sorted(candidate_anchors[index])[0]
                position = normalized_file.find(anchor)
                if position < 0:
                    continue
                requirement_anchor_offset = normalized_requirement.find(anchor)
                window_start = max(0, position - requirement_anchor_offset)
                window = normalized_file[
                    window_start : window_start + int(len(normalized_requirement) * 1.2)
                ]
                similarity = SequenceMatcher(None, normalized_requirement, window).ratio()
                if similarity < 0.92:
                    continue
                category = "HIGH_THRESHOLD_NEAR_DUPLICATE"
                line = min(candidate_lines[index])
            key = (
                relative,
                line,
                row["jira_key"],
                row["requirement_id"],
                category,
            )
            matches[key] = {
                "contaminated_file": relative,
                "location": f"{relative}:{line}",
                "matched_record_identifier": row["jira_key"],
                "requirement_identifier": row["requirement_id"],
                "match_category": category,
                "classification": classification,
                "similarity": round(similarity, 4),
                "fingerprint": row["fingerprint"],
                "remediation_required": remediation,
                "prohibited": _is_prohibited(classification),
            }

    ordered = sorted(
        matches.values(),
        key=lambda item: (
            item["matched_record_identifier"],
            item["contaminated_file"],
            item["location"],
            item["match_category"],
            item.get("requirement_identifier") or "",
        ),
    )
    contaminated = sorted(
        {
            item["matched_record_identifier"]
            for item in ordered
            if item["prohibited"]
        }
    )
    exposed = sorted({item["matched_record_identifier"] for item in ordered})
    return {
        "schema_version": "aem-guides-benchmark-leakage-scan-v2",
        "scanner_policy": {
            "prints_ground_truth_text": False,
            "full_authoritative_source_fingerprints": True,
            "exact_requirement_minimum_characters": 16,
            "exact_requirement_minimum_tokens": 3,
            "near_duplicate_minimum_characters": 80,
            "near_duplicate_minimum_tokens": 12,
            "near_duplicate_threshold": 0.92,
            "jira_key_matching": "exact",
        },
        "summary": {
            "ground_truth_record_count": len(record_ids),
            "requirement_fingerprint_count": len(requirements),
            "tracked_file_count": len(files),
            "match_count": len(ordered),
            "exposed_record_count": len(exposed),
            "prohibited_contaminated_record_count": len(contaminated),
        },
        "exposed_record_identifiers": exposed,
        "prohibited_contaminated_record_identifiers": contaminated,
        "matches": ordered,
    }


def load_ground_truth(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = scan_records(args.repo_root, load_ground_truth(args.ground_truth))
    _write_json(args.output, report)
    print(
        json.dumps(
            {
                "status": "PASS"
                if report["summary"]["prohibited_contaminated_record_count"] == 0
                else "CONTAMINATED",
                **report["summary"],
                "output": str(args.output.resolve()),
            },
            indent=2,
        )
    )
    return 0 if report["summary"]["prohibited_contaminated_record_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
