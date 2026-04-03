"""
AEM Release Agent — detects new AEM Guides releases and
automatically indexes them into RAG so future DITA generation
uses the latest documentation.

Triggered 3 ways:
1. Scheduled  — runs every 6 hours via APScheduler
2. Webhook    — AEM/Adobe fires POST /api/v1/agent/aem-release
3. Event      — user clicks "Check for updates" in UI

Place at: backend/app/services/aem_release_agent.py
"""
from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# State file — tracks last known AEM version
AGENT_STATE_PATH = Path(__file__).resolve().parent.parent / "storage" / "agent_state.json"

# Known AEM Guides release page URLs to monitor
AEM_RELEASE_URLS = [
    "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/release-info/release-notes/on-prem-release-notes/latest-release-info",
    "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/release-info/release-notes/cloud-release-notes/latest-release-info",
]

# Topics to re-index when new release detected
RELEASE_INDEX_TOPICS = [
    {
        "id":    "aem_guides_latest_release",
        "query": "AEM Guides latest release notes new features 2024 2025",
        "tag":   "aem-release",
        "domains": ["experienceleague.adobe.com", "helpx.adobe.com"],
    },
    {
        "id":    "aem_guides_whats_new",
        "query": "AEM Guides what's new features improvements",
        "tag":   "aem-release",
        "domains": ["experienceleague.adobe.com"],
    },
    {
        "id":    "aem_guides_fixed_issues",
        "query": "AEM Guides fixed issues bug fixes resolved",
        "tag":   "aem-release",
        "domains": ["experienceleague.adobe.com"],
    },
    {
        "id":    "aem_guides_known_issues",
        "query": "AEM Guides known issues limitations workarounds",
        "tag":   "aem-release",
        "domains": ["experienceleague.adobe.com"],
    },
]


# ── State management ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    """Load agent state from disk."""
    if not AGENT_STATE_PATH.exists():
        return {}
    try:
        return json.loads(AGENT_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    """Save agent state to disk."""
    AGENT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENT_STATE_PATH.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def _get_content_hash(content: str) -> str:
    """Hash page content to detect changes."""
    return hashlib.md5(content.encode()).hexdigest()


# ── Release detection ─────────────────────────────────────────────────────────

def check_for_new_aem_release() -> dict:
    """
    Check if a new AEM Guides release has been published.
    Compares content hash of release notes page against last known hash.

    Returns:
        {
            "new_release_detected": bool,
            "version": str or None,
            "url": str,
            "changed_urls": list[str],
        }
    """
    try:
        import httpx
        state = _load_state()
        changed_urls = []
        detected_version = None

        for url in AEM_RELEASE_URLS:
            try:
                resp = httpx.get(
                    url,
                    timeout=30.0,
                    follow_redirects=True,
                    headers={"User-Agent": "AEM-Dataset-Studio/1.0 (release-monitor)"},
                )
                if resp.status_code != 200:
                    continue

                content = resp.text
                current_hash = _get_content_hash(content)
                stored_hash  = state.get(f"hash_{url}", "")

                if current_hash != stored_hash:
                    changed_urls.append(url)
                    state[f"hash_{url}"]    = current_hash
                    state[f"checked_{url}"] = datetime.utcnow().isoformat()

                    # Try to extract version number from page content
                    version = _extract_version_from_content(content)
                    if version:
                        detected_version = version

            except Exception as e:
                logger.debug_structured(
                    "Release check failed for URL",
                    extra_fields={"url": url, "error": str(e)},
                )

        if changed_urls:
            state["last_release_detected"] = datetime.utcnow().isoformat()
            state["last_version"]           = detected_version or "unknown"
            _save_state(state)
            logger.info_structured(
                "New AEM release detected",
                extra_fields={
                    "version":      detected_version,
                    "changed_urls": changed_urls,
                },
            )

        return {
            "new_release_detected": bool(changed_urls),
            "version":              detected_version,
            "changed_urls":         changed_urls,
            "checked_at":           datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.warning_structured(
            "Release check failed",
            extra_fields={"error": str(e)},
        )
        return {
            "new_release_detected": False,
            "version":              None,
            "changed_urls":         [],
            "error":                str(e),
        }


def _extract_version_from_content(content: str) -> Optional[str]:
    """Extract AEM Guides version number from page content."""
    import re
    # Match patterns like "4.2", "4.3.1", "2024.2", "2024.02.0"
    patterns = [
        r"AEM Guides\s+(\d{4}\.\d+(?:\.\d+)?)",
        r"version\s+(\d+\.\d+(?:\.\d+)?)",
        r"Release\s+(\d+\.\d+(?:\.\d+)?)",
        r"(\d{4}\.\d{2}\.\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


# ── Auto-indexing ─────────────────────────────────────────────────────────────

async def auto_index_new_release(version: Optional[str] = None) -> dict:
    """
    When a new AEM release is detected:
    1. Search Tavily for release notes and new features
    2. Crawl Experience League for updated docs
    3. Index everything into ChromaDB RAG
    4. Re-crawl Experience League pages
    5. Return summary of what was indexed

    This makes future DITA generation aware of the new release automatically.
    """
    results = {
        "triggered_at":   datetime.utcnow().isoformat(),
        "version":        version or "latest",
        "tavily_indexed": 0,
        "crawl_chunks":   0,
        "errors":         [],
    }

    tavily_key = __import__("os").getenv("TAVILY_API_KEY", "")

    # ── Step 1: Tavily research + index ──────────────────────────────────────
    if tavily_key:
        try:
            from tavily import TavilyClient
            from app.services.embedding_service import embed_texts, is_embedding_available
            from app.services.vector_store_service import add_documents, is_chroma_available

            client = TavilyClient(api_key=tavily_key)

            all_documents = []
            all_metadatas = []
            all_ids       = []

            for topic in RELEASE_INDEX_TOPICS:
                query = topic["query"]
                if version:
                    query = f"{query} {version}"

                try:
                    result = client.search(
                        query=query,
                        search_depth="advanced",
                        include_domains=topic["domains"],
                        max_results=4,
                        include_answer=True,
                    )

                    # Index answer
                    answer = result.get("answer", "")
                    if answer:
                        all_documents.append(
                            f"[AEM Release {version or 'latest'}] {query}\n\n{answer}"
                        )
                        all_metadatas.append({
                            "topic_id": topic["id"],
                            "tag":      topic["tag"],
                            "version":  version or "latest",
                            "type":     "release_answer",
                            "source":   "tavily_answer",
                            "url":      "",
                            "indexed_at": datetime.utcnow().isoformat(),
                        })
                        all_ids.append(
                            f"release_{topic['id']}_answer_{version or 'latest'}"
                        )

                    # Index results
                    for i, r in enumerate(result.get("results", [])):
                        content = r.get("content", "").strip()
                        if len(content) < 100:
                            continue
                        url      = r.get("url", "")
                        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                        all_documents.append(
                            f"{r.get('title','')}\n{url}\n\n{content[:3000]}"
                        )
                        all_metadatas.append({
                            "topic_id": topic["id"],
                            "tag":      topic["tag"],
                            "version":  version or "latest",
                            "type":     "release_result",
                            "source":   "tavily_search",
                            "url":      url,
                            "title":    r.get("title", ""),
                            "indexed_at": datetime.utcnow().isoformat(),
                        })
                        all_ids.append(
                            f"release_{topic['id']}_{url_hash}"
                        )

                except Exception as e:
                    results["errors"].append(
                        f"Tavily {topic['id']}: {str(e)[:80]}"
                    )

            # Store in ChromaDB
            if all_documents and is_chroma_available() and is_embedding_available():
                embeddings = embed_texts(all_documents)
                if embeddings is not None:
                    success = add_documents(
                        "research_cache",
                        ids=all_ids,
                        documents=all_documents,
                        metadatas=all_metadatas,
                        embeddings=[e.tolist() for e in embeddings],
                    )
                    if success:
                        results["tavily_indexed"] = len(all_documents)

        except Exception as e:
            results["errors"].append(f"Tavily indexing failed: {str(e)[:100]}")

    else:
        results["errors"].append(
            "TAVILY_API_KEY not set — skipping web research"
        )

    # ── Step 2: Re-crawl Experience League ────────────────────────────────────
    try:
        from app.services.crawl_service import crawl_and_index
        crawl_stats = crawl_and_index()
        results["crawl_chunks"] = crawl_stats.get("chunks_stored", 0)
        if crawl_stats.get("errors"):
            results["errors"].extend(crawl_stats["errors"][:3])
    except Exception as e:
        results["errors"].append(f"Experience League crawl failed: {str(e)[:100]}")

    # ── Step 3: Update state ──────────────────────────────────────────────────
    state = _load_state()
    state["last_auto_index"]         = datetime.utcnow().isoformat()
    state["last_auto_index_version"] = version or "latest"
    state["last_auto_index_results"] = {
        "tavily_chunks": results["tavily_indexed"],
        "crawl_chunks":  results["crawl_chunks"],
    }
    _save_state(state)

    logger.info_structured(
        "AEM release auto-indexing complete",
        extra_fields=results,
    )
    return results


# ── Full agent run ────────────────────────────────────────────────────────────

async def run_aem_release_agent() -> dict:
    """
    Full agent run:
    1. Check if new AEM release detected
    2. If yes → auto-index into RAG
    3. Return full report

    Called by:
    - APScheduler (every 6 hours)
    - Webhook POST /api/v1/agent/aem-release
    - User clicking "Check for updates" in UI
    """
    logger.info_structured("AEM release agent starting", extra_fields={})

    # Check for new release
    check_result = check_for_new_aem_release()

    if not check_result["new_release_detected"]:
        return {
            "action":     "no_action",
            "reason":     "No new AEM release detected",
            "checked_at": check_result["checked_at"],
            "version":    check_result.get("version"),
        }

    # New release detected — auto-index
    logger.info_structured(
        "New AEM release detected — starting auto-indexing",
        extra_fields={"version": check_result.get("version")},
    )

    index_results = await auto_index_new_release(
        version=check_result.get("version")
    )

    return {
        "action":          "indexed",
        "version":         check_result.get("version", "unknown"),
        "changed_urls":    check_result["changed_urls"],
        "tavily_indexed":  index_results["tavily_indexed"],
        "crawl_chunks":    index_results["crawl_chunks"],
        "errors":          index_results["errors"],
        "completed_at":    datetime.utcnow().isoformat(),
        "message": (
            f"New AEM Guides release detected. "
            f"Indexed {index_results['tavily_indexed']} research chunks "
            f"and {index_results['crawl_chunks']} Experience League chunks. "
            f"Future DITA generation will use latest documentation."
        ),
    }


def get_agent_status() -> dict:
    """Get current agent state — for UI display."""
    state = _load_state()
    return {
        "last_release_detected": state.get("last_release_detected"),
        "last_version":          state.get("last_version"),
        "last_auto_index":       state.get("last_auto_index"),
        "last_auto_index_version": state.get("last_auto_index_version"),
        "last_auto_index_results": state.get("last_auto_index_results", {}),
        "monitored_urls":        len(AEM_RELEASE_URLS),
        "index_topics":          len(RELEASE_INDEX_TOPICS),
    }
