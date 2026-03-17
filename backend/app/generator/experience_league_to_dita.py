"""
Experience League content to DITA recipe.

Consumes scraped structured content (paragraphs, list_items, codeph, codeblocks)
from aem_guides_doc_chunks.json and produces valid DITA topics.
Uses html_to_dita converter. Validates output before including in bundle.
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from app.generator.dita_utils import make_dita_id
from app.jobs.schemas import DatasetConfig
from app.storage import get_storage
from app.utils.html_to_dita import html_fragments_to_dita_topic
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

DOC_CHUNKS_FILENAME = "aem_guides_doc_chunks.json"
STRUCTURED_BY_URL_FILENAME = "aem_guides_structured_by_url.json"
MAX_TOPICS_DEFAULT = 20


RECIPE_SPECS = [
    {
        "id": "experience_league_to_dita",
        "title": "Experience League to DITA",
        "description": "Generate DITA topics from scraped Experience League content (paragraphs, lists, code). Uses Playwright-scraped structured data.",
        "tags": ["Experience League", "scraped content", "authentic", "p", "li", "codeph", "codeblock"],
        "module": "app.generator.experience_league_to_dita",
        "function": "generate_experience_league_to_dita",
        "params_schema": {"max_topics": "int"},
        "default_params": {"max_topics": MAX_TOPICS_DEFAULT},
        "stability": "stable",
        "constructs": ["topic", "p", "ul", "li", "codeph", "codeblock"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": ["Experience League", "scraped content", "authentic documentation"],
        "avoid_when": ["Representative Sample XML", "specific recipe matches"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]


def _slug_from_url(url: str) -> str:
    """Extract a slug from Experience League URL for use in topic ID."""
    if not url:
        return "el"
    parts = url.rstrip("/").split("/")
    for p in reversed(parts):
        if p and p not in ("en", "docs", "experience-manager-guides", "using"):
            slug = re.sub(r"[^a-zA-Z0-9_-]", "_", p)[:50]
            return slug or "el"
    return "el"


def generate_experience_league_to_dita(
    config: DatasetConfig,
    base_path: str,
    max_topics: int = MAX_TOPICS_DEFAULT,
    id_prefix: str = "el",
    pretty_print: bool = True,
) -> Dict[str, bytes]:
    """
    Load scraped chunks from storage, convert to DITA topics, validate.

    Prefers aem_guides_structured_by_url.json (per-URL full content) when available;
    otherwise falls back to aem_guides_doc_chunks.json (split chunks, dedupe by URL).
    Only outputs topics that pass validation. Skips chunks without structured content.
    """
    files: Dict[str, bytes] = {}
    storage = get_storage()
    structured_path = storage.base_path / STRUCTURED_BY_URL_FILENAME
    chunks_path = storage.base_path / DOC_CHUNKS_FILENAME

    # Prefer structured_by_url (one record per URL with full content)
    chunks: List[dict] = []
    if structured_path.exists():
        try:
            raw = json.loads(structured_path.read_text(encoding="utf-8"))
            if isinstance(raw, list) and raw:
                chunks = raw
        except (json.JSONDecodeError, OSError) as e:
            logger.warning_structured(
                "Failed to load structured_by_url, falling back to chunks",
                extra_fields={"error": str(e)},
            )

    if not chunks and chunks_path.exists():
        try:
            raw = json.loads(chunks_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                chunks = raw
        except (json.JSONDecodeError, OSError) as e:
            logger.warning_structured("Failed to load doc chunks", extra_fields={"error": str(e)})
            return files

    if not chunks:
        logger.warning_structured(
            "Experience League chunks not found, run crawl with use_playwright first",
            extra_fields={"path": str(chunks_path)},
        )
        root = f"{base_path}/experience_league_to_dita"
        placeholder_id = make_dita_id("placeholder", id_prefix, set())
        from app.generator.evidence_to_dita import _minimal_topic_xml
        files[f"{root}/topics/placeholder.dita"] = _minimal_topic_xml(
            config, placeholder_id, "No scraped content (run crawl with use_playwright)"
        )
        return files

    seen_urls: set = set()
    used_ids: set = set()
    root_folder = f"{base_path}/experience_league_to_dita"
    topics_folder = f"{root_folder}/topics"
    Path(topics_folder).mkdir(parents=True, exist_ok=True)
    topic_count = 0

    for chunk in chunks:
        if topic_count >= max_topics:
            break
        url = chunk.get("url", "")
        if not url or url in seen_urls:
            continue
        paragraphs = chunk.get("paragraphs") or []
        list_items = chunk.get("list_items") or []
        codeph = chunk.get("codeph") or []
        codeblocks = chunk.get("codeblocks") or []
        tables = chunk.get("tables") or []
        if not (paragraphs or list_items or codeph or codeblocks or tables):
            continue
        seen_urls.add(url)

        title = chunk.get("title", "") or _slug_from_url(url)
        topic_id = make_dita_id(_slug_from_url(url), id_prefix, used_ids)
        used_ids.add(topic_id)

        fragments = {
            "paragraphs": paragraphs,
            "list_items": list_items,
            "codeph": codeph,
            "codeblocks": codeblocks,
            "tables": tables,
        }
        topic_bytes = html_fragments_to_dita_topic(
            fragments,
            topic_id=topic_id,
            title=title,
            doctype_topic=config.doctype_topic,
        )
        if not topic_bytes:
            continue

        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", _slug_from_url(url))[:60] or "topic"
        out_path = f"{topics_folder}/{safe_slug}_{topic_count}.dita"
        files[out_path] = topic_bytes
        topic_count += 1

    if not files:
        root = f"{base_path}/experience_league_to_dita"
        placeholder_id = make_dita_id("placeholder", id_prefix, set())
        from app.generator.evidence_to_dita import _minimal_topic_xml
        files[f"{root}/topics/placeholder.dita"] = _minimal_topic_xml(
            config, placeholder_id, "No structured content in chunks"
        )

    return files
