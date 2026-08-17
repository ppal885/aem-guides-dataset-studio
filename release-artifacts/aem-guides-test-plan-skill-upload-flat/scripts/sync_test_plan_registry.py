#!/usr/bin/env python3
"""Scan starling test plans and refresh test-plans-registry.json metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path


PLAN_GLOB = "*-test-plan.md"
TITLE_RE = re.compile(r"^#\s+Test Plan:\s+(\S+)\s+[—-]\s+(.+)$", re.M)
REVIEW_RE = re.compile(r"\*\*Review status:\*\*\s*(.+)$", re.M)
INLINE_REVIEW_RE = re.compile(r"- \*\*Review status:\*\*\s*(.+)$", re.M)
DAM_RE = re.compile(r"/content/dam/[^\s`|)]+")
HISTORICAL_JIRA_RE = re.compile(r"^\|\s*(GUIDES-\d+|AEM-\d+|DATA-\d+)\s*\|", re.M)
LINES_COMPACT = 195


def scan_plan(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = len(text.splitlines())
    jira_key = path.stem.replace("-test-plan", "")
    title = jira_key
    match = TITLE_RE.search(text)
    if match:
        jira_key = match.group(1)
        title = match.group(2).strip()

    review = "Unknown"
    for pattern in (REVIEW_RE, INLINE_REVIEW_RE):
        m = pattern.search(text)
        if m:
            review = m.group(1).strip()
            break

    dam_paths = sorted(set(DAM_RE.findall(text)))
    historical_jiras = sorted(set(HISTORICAL_JIRA_RE.findall(text)))
    template_version = (
        "compact-3-section"
        if lines <= LINES_COMPACT and "## 1. Summary & expected behaviour" in text
        else "legacy-15-section"
    )

    return {
        "jira_key": jira_key,
        "title": title,
        "plan_file": path.as_posix().replace("\\", "/"),
        "template_version": template_version,
        "line_count": lines,
        "review_status": review.split("(")[0].strip(),
        "dam_paths": dam_paths,
        "related_past_jiras": historical_jiras,
        "scanned": date.today().isoformat(),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plans-dir",
        type=Path,
        default=Path("docs/qa/test-plans"),
        help="Directory containing *-test-plan.md files",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("docs/qa/test-plans/test-plans-registry.json"),
        help="Registry JSON to update",
    )
    args = parser.parse_args(argv)

    if not args.registry.exists():
        print(f"ERROR: registry not found: {args.registry}", file=sys.stderr)
        return 1

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    existing = {p["jira_key"]: p for p in registry.get("plans", [])}
    scanned: list[dict] = []

    for plan_path in sorted(args.plans_dir.glob(PLAN_GLOB)):
        info = scan_plan(plan_path)
        merged = {**existing.get(info["jira_key"], {}), **info}
        merged["updated"] = info["scanned"]
        if "created" not in merged:
            merged["created"] = info["scanned"]
        if info["dam_paths"]:
            merged["dam_path"] = info["dam_paths"][0]
        scanned.append(merged)

    registry["plans"] = scanned
    registry["last_updated"] = date.today().isoformat()
    registry.setdefault("template", {})["max_lines"] = LINES_COMPACT
    args.registry.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(f"OK: registry updated with {len(scanned)} plan(s) -> {args.registry}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
