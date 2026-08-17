#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run coverage-gap driven scraping and RAG enrichment from a source manifest.

This script intentionally orchestrates the existing scrapers/indexers instead of
creating a new crawler or vector store. Use it on the VM that hosts Chroma when
you want the results indexed into the live RAG.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "rag-coverage-sources.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-id", action="append", default=None, help="Run only selected source id; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip source scraping/conversion")
    parser.add_argument("--enrich", action="store_true", help="Build enriched behavior chunks after scraping")
    parser.add_argument("--upsert-chroma", action="store_true", help="Pass --upsert-chroma to the enrichment step")
    parser.add_argument("--resume", action="store_true", help="Resume Experience League crawls when state exists")
    parser.add_argument("--reset", action="store_true", help="Reset selected source state before scraping")
    parser.add_argument("--limit", type=int, default=0, help="Override per-source limit for scrape/conversion commands")
    parser.add_argument("--python", default=sys.executable, help="Python executable to run child scripts")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = load_config(args.config)
    selected = select_sources(config, args.source_id)
    commands: list[list[str]] = []
    if not args.skip_scrape:
        for source in selected:
            commands.append(build_source_command(source, args))
    if args.enrich:
        commands.append(build_enrichment_command(config, args))
        commands.extend(build_dita_ot_docs_index_commands(config, args))
    if not commands:
        print("No commands selected. Use --enrich and/or omit --skip-scrape.")
        return 1
    print_summary(config, selected, commands, dry_run=args.dry_run)
    if args.dry_run:
        return 0
    for command in commands:
        print("+ " + shell_join(command), flush=True)
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    return 0


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def select_sources(config: dict[str, Any], ids: list[str] | None) -> list[dict[str, Any]]:
    requested = set(ids or [])
    sources = [s for s in config.get("sources", []) if s.get("enabled", True)]
    if requested:
        sources = [s for s in sources if s.get("id") in requested]
        missing = sorted(requested - {str(s.get("id")) for s in sources})
        if missing:
            raise SystemExit(f"Unknown or disabled source ids: {', '.join(missing)}")
    return sorted(sources, key=lambda s: int(s.get("priority", 999)))


def build_source_command(source: dict[str, Any], args: argparse.Namespace) -> list[str]:
    source_type = source.get("type")
    if source_type == "experienceleague":
        return build_experienceleague_command(source, args)
    if source_type == "dita_ot_issues":
        return build_dita_ot_issue_command(source, args)
    if source_type == "dita_ot_docs":
        return build_dita_ot_docs_command(source, args)
    raise SystemExit(f"Unsupported source type for {source.get('id')}: {source_type}")


def build_experienceleague_command(source: dict[str, Any], args: argparse.Namespace) -> list[str]:
    command = [
        args.python,
        "scripts/scrape_experienceleague_to_dita.py",
        "--state-dir",
        str(source["state_dir"]),
        "--scope-prefix",
        str(source["scope_prefix"]),
        "--seed-url",
        str(source["seed_url"]),
        "--limit",
        str(args.limit or int(source.get("limit") or 1000)),
    ]
    if args.resume:
        command.append("--resume")
    if args.reset:
        command.append("--reset")
    return command


def build_dita_ot_issue_command(source: dict[str, Any], args: argparse.Namespace) -> list[str]:
    command = [
        args.python,
        "scripts/convert_dita_ot_issues_to_dita.py",
        "--input",
        str(source["input"]),
        "--output-dir",
        str(source["output_dir"]),
        "--state",
        str(source.get("state") or "auto"),
    ]
    limit = args.limit or int(source.get("limit") or 0)
    if limit > 0:
        command.extend(["--limit", str(limit)])
    if args.reset:
        command.append("--reset")
    return command


def build_dita_ot_docs_command(source: dict[str, Any], args: argparse.Namespace) -> list[str]:
    command = [
        args.python,
        "scripts/scrape_dita_ot_docs_to_dita.py",
        "--state-dir",
        str(source["state_dir"]),
        "--scope-prefix",
        str(source["scope_prefix"]),
        "--seed-url",
        str(source["seed_url"]),
        "--limit",
        str(args.limit or int(source.get("limit") or 250)),
    ]
    if args.resume:
        command.append("--resume")
    if args.reset:
        command.append("--reset")
    return command


def build_enrichment_command(config: dict[str, Any], args: argparse.Namespace) -> list[str]:
    enrichment = config.get("enrichment") or {}
    command = [args.python, "scripts/enrich_experienceleague_behavior_chunks.py"]
    for root in enrichment.get("experienceleague_roots", []):
        if (PROJECT_ROOT / root).exists():
            command.extend(["--corpus-root", str(root)])
    command.extend(
        [
            "--output",
            str(enrichment.get("output") or "backend/storage/aem_guides_enriched_behavior_chunks.json"),
            "--sample-output",
            str(enrichment.get("sample_output") or "tmp/aem_guides_enriched_behavior_sample.json"),
            "--max-chunks",
            str(enrichment.get("max_chunks") or 12000),
            "--batch-size",
            str(enrichment.get("batch_size") or 64),
        ]
    )
    if args.upsert_chroma:
        command.append("--upsert-chroma")
    return command


def build_dita_ot_docs_index_commands(config: dict[str, Any], args: argparse.Namespace) -> list[list[str]]:
    indexing = config.get("dita_ot_docs_indexing") or {}
    roots = [root for root in indexing.get("roots", []) if (PROJECT_ROOT / root).exists()]
    if not roots:
        return []
    commands: list[list[str]] = []
    for root in roots:
        command = [
            args.python,
            "scripts/index_dita_behavior_corpus.py",
            "--corpus-root",
            str(root),
            "--output",
            str(indexing.get("output") or "backend/storage/dita_ot_docs_behavior_chunks.json"),
            "--sample-output",
            str(indexing.get("sample_output") or "tmp/dita_ot_docs_behavior_sample.json"),
        ]
        for prefix in indexing.get("allowed_source_prefixes", ["https://www.dita-ot.org/"]):
            command.extend(["--allowed-source-prefix", str(prefix)])
        if args.upsert_chroma:
            command.append("--upsert-chroma")
            command.extend(["--batch-size", str(indexing.get("batch_size") or 64)])
        commands.append(command)
    return commands


def print_summary(config: dict[str, Any], sources: list[dict[str, Any]], commands: list[list[str]], *, dry_run: bool) -> None:
    print(
        json.dumps(
            {
                "config_version": config.get("version"),
                "mode": "dry-run" if dry_run else "execute",
                "sources": [s.get("id") for s in sources],
                "commands": [shell_join(c) for c in commands],
            },
            indent=2,
        )
    )


def shell_join(command: list[str]) -> str:
    return " ".join(quote(part) for part in command)


def quote(value: str) -> str:
    if not value or any(ch.isspace() for ch in value) or any(ch in value for ch in '"&|<>'):
        return '"' + value.replace('"', '\\"') + '"'
    return value


if __name__ == "__main__":
    raise SystemExit(main())
