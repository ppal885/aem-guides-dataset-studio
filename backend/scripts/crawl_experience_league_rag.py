#!/usr/bin/env python3
"""Crawl Experience League AEM Guides pages and upsert into RAG (safe merge).

This script discovers and scrapes Adobe Experience League documentation for
AEM Guides, chunks it, embeds it, and **upserts** into the ``aem_guides`` Chroma
collection plus ``storage/aem_guides_doc_chunks.json``.

Unlike a full ``crawl_and_index()`` run, it does **not** wipe the whole Chroma
collection unless you pass ``--wipe-collection`` (use with care).

Examples
--------
# Recursive crawl of the whole AEM Guides doc tree (recommended first run):
  cd backend
  python scripts/crawl_experience_league_rag.py --recursive --max-depth 3

# Use URLs from config/aem_guides_crawl_urls.json (Experience League only):
  python scripts/crawl_experience_league_rag.py --from-config

# Specific URLs:
  python scripts/crawl_experience_league_rag.py --url https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/output-presets-aemg/generate-output-understand-presets

# Dry-run (discover URLs only):
  python scripts/crawl_experience_league_rag.py --recursive --dry-run

# Playwright scraper (richer structure; slower):
  python scripts/crawl_experience_league_rag.py --from-config --playwright
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

from app.services.experience_league_index_service import (  # noqa: E402
    AEM_GUIDES_BASE,
    crawl_experience_league_rag,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crawl Experience League AEM Guides docs and upsert into RAG",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Discover all pages under --base-url (RecursiveUrlLoader)",
    )
    parser.add_argument(
        "--from-config",
        action="store_true",
        help="Crawl Experience League URLs from config/aem_guides_crawl_urls.json",
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        default=[],
        help="Explicit Experience League URL (repeatable)",
    )
    parser.add_argument(
        "--base-url",
        default=AEM_GUIDES_BASE,
        help=f"Root for --recursive mode (default: {AEM_GUIDES_BASE})",
    )
    parser.add_argument("--max-depth", type=int, default=3, help="Recursive crawl depth (1-6)")
    parser.add_argument("--playwright", action="store_true", help="Use Playwright scraper")
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=200)
    parser.add_argument(
        "--wipe-collection",
        action="store_true",
        help="Delete entire aem_guides Chroma collection before upsert (destructive)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Discover URLs only; no scrape/index")
    args = parser.parse_args()

    if not args.recursive and not args.from_config and not args.urls:
        print("No mode selected — defaulting to --from-config (Experience League URLs only).")
        print("For a full tree crawl, use: --recursive --max-depth 3")
        args.from_config = True

    stats = crawl_experience_league_rag(
        urls=args.urls or None,
        base_url=args.base_url,
        recursive=args.recursive,
        max_depth=args.max_depth,
        from_config=args.from_config,
        use_playwright=args.playwright,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        wipe_collection=args.wipe_collection,
        dry_run=args.dry_run,
    )

    print(json.dumps(stats, indent=2))

    if stats.get("errors"):
        print("\nWarnings/errors:")
        for err in stats["errors"][:20]:
            print(f"  - {err}")
        if len(stats["errors"]) > 20:
            print(f"  ... and {len(stats['errors']) - 20} more")

    if args.dry_run:
        print(f"\nDry run: {stats.get('urls_discovered', 0)} URLs would be crawled.")
        return 0

    if stats.get("pages_crawled", 0) == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
