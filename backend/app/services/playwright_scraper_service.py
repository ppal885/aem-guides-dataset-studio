"""Playwright-based scraper for Experience League pages.

Extracts structured content from p, li, code, pre elements for DITA conversion.
Uses headless Chromium with rate limiting.
"""
import os
import time
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

RATE_LIMIT_SEC = 1.0
DEFAULT_TIMEOUT_MS = 45000  # Increased for slow Experience League pages
CONTENT_WAIT_MS = 10000  # Shorter wait for main content selector
_last_request_time: float = 0.0

# Broad selectors for Experience League (.spectrum-Body, .markdown-body, etc.)
CONTENT_SELECTORS = [
    "article",
    "main",
    ".content",
    ".spectrum-Body",
    ".markdown-body",
    '[role="main"]',
]
PARAGRAPH_SELECTOR = "article p, main p, .content p, .spectrum-Body p, .markdown-body p, [role=main] p, p"


def _rate_limit() -> None:
    """Enforce 1 req/sec rate limit."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < RATE_LIMIT_SEC:
        time.sleep(RATE_LIMIT_SEC - elapsed)
    _last_request_time = time.monotonic()


def scrape_experience_league_page(
    url: str,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict:
    """
    Scrape an Experience League page with Playwright.
    Extracts paragraphs, list items, inline code (codeph), and code blocks.

    Returns:
        {
            "url": str,
            "title": str,
            "paragraphs": list[str],
            "list_items": list[str],
            "codeph": list[str],
            "codeblocks": list[str],
            "error": str | None,
        }
    """
    result = {
        "url": url,
        "title": "",
        "paragraphs": [],
        "list_items": [],
        "codeph": [],
        "codeblocks": [],
        "tables": [],
        "error": None,
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        result["error"] = f"Playwright not installed: {e}. Run: pip install playwright && playwright install chromium"
        logger.warning_structured(
            "Playwright not available",
            extra_fields={"url": url, "error": result["error"]},
        )
        return result

    _rate_limit()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(timeout_ms)
                page.set_extra_http_headers({
                    "User-Agent": "AEM-Guides-Dataset-Studio/1.0 (documentation-indexer)",
                })
                try:
                    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                except Exception:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                # Wait for main content before extracting (dynamic Experience League pages)
                for sel in CONTENT_SELECTORS:
                    try:
                        page.wait_for_selector(sel, timeout=CONTENT_WAIT_MS)
                        break
                    except Exception:
                        continue

                title = page.title()
                result["title"] = title or ""

                paragraphs = page.evaluate(f"""
                    () => {{
                        const ps = document.querySelectorAll('{PARAGRAPH_SELECTOR}');
                        return Array.from(ps).map(el => el.innerText?.trim() || '').filter(t => t.length > 0);
                    }}
                """)
                result["paragraphs"] = paragraphs if isinstance(paragraphs, list) else []

                list_items = page.evaluate("""
                    () => {
                        const items = [];
                        document.querySelectorAll('ul li, ol li').forEach(li => {
                            const text = li.innerText?.trim();
                            if (text) items.push(text);
                        });
                        return items;
                    }
                """)
                result["list_items"] = list_items if isinstance(list_items, list) else []

                codeph = page.evaluate("""
                    () => {
                        const codes = document.querySelectorAll('code:not(pre code), .codeph, kbd');
                        return Array.from(codes).map(el => el.innerText?.trim() || '').filter(t => t.length > 0);
                    }
                """)
                result["codeph"] = codeph if isinstance(codeph, list) else []

                codeblocks = page.evaluate("""
                    () => {
                        const blocks = [];
                        document.querySelectorAll('pre, pre code, .codeblock, .highlight pre').forEach(el => {
                            const text = el.tagName.toLowerCase() === 'pre'
                                ? el.innerText?.trim()
                                : (el.closest('pre')?.innerText || el.innerText || '').trim();
                            if (text) blocks.push(text);
                        });
                        return [...new Set(blocks)];
                    }
                """)
                result["codeblocks"] = codeblocks if isinstance(codeblocks, list) else []

                tables = page.evaluate("""
                    () => {
                        const out = [];
                        document.querySelectorAll('table').forEach(tbl => {
                            const rows = [];
                            tbl.querySelectorAll('tr').forEach(tr => {
                                const cells = [];
                                tr.querySelectorAll('th, td').forEach(cell => {
                                    cells.push(cell.innerText?.trim() || '');
                                });
                                if (cells.length) rows.push(cells);
                            });
                            if (rows.length) out.push(rows);
                        });
                        return out;
                    }
                """)
                result["tables"] = tables if isinstance(tables, list) else []

            finally:
                browser.close()

    except Exception as e:
        result["error"] = str(e)
        logger.warning_structured(
            "Playwright scrape failed",
            extra_fields={"url": url, "error": str(e)},
        )

    return result
