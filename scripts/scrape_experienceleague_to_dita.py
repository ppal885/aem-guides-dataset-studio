#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scrape Experience League documentation and convert pages to DITA topics.

Standalone test-corpus tooling (NOT production ingestion, NO LLM calls). It
crawls in-scope pages, rule-based-converts each HTML page to a DITA <topic>,
and keeps a persistent queue + manifest so the crawl is idempotent and resumable
across runs. It stops after converting 1000 topics in a run (override with
--limit) so a human can review the batch before continuing.

Run fresh:
    python scripts/scrape_experienceleague_to_dita.py
Resume:
    python scripts/scrape_experienceleague_to_dita.py --resume
Reset (wipe state and start over):
    python scripts/scrape_experienceleague_to_dita.py --reset
Convert 500 now, then resume the next 500:
    python scripts/scrape_experienceleague_to_dita.py --limit 500
    python scripts/scrape_experienceleague_to_dita.py --resume --limit 500
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Set, Tuple
from urllib import robotparser
from urllib.parse import urljoin, urlparse, urlunparse
from xml.sax.saxutils import escape, quoteattr

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from lxml import etree

# --- DITA output constants ---------------------------------------------------
# The XML declaration + DOCTYPE prepended to every topic. Kept as a module
# constant so both the converter and the pretty-print pass emit it identically.
_DITA_PROLOG = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
)
_INDENT = "    "  # 4-space nesting for the pretty-printed DITA.

# --- Crawl scope / politeness constants --------------------------------------
HOST = "experienceleague.adobe.com"
# Scope is locale-wide (`/in/`), not narrowed to `/in/support/`. Rationale:
# the seed support.html is a hub page whose real how-to/user-guide content lives
# across the whole `/in/` product tree (e.g. /in/photoshop/using/..., not under
# /in/support/), so a support-only scope would capture landing hubs but cut off
# the actual articles a RAG test corpus needs. `/in/` also matches the site's own
# published boundary: helpx publishes one flat sitemap per locale at
# /in/sitemap.xml, so the sitemap top-up maps 1:1 to this scope. Mirrors the
# sibling scraper's "one broad docs tree in one language" scoping intent.
# Trailing slash is deliberate: it prevents `/in_hi/` (the India-Hindi locale)
# from matching this India-English scope via startswith.
SCOPE_PREFIX = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
# Exact substring an unresolved in-scope xref placeholder starts with. Used as a
# cheap gate to detect/skip files without pending cross-references (href is the
# first attribute lxml emits, so this holds after pretty-printing too).
_INSCOPE_XREF_MARKER = '<xref href="' + SCOPE_PREFIX
SEED_URL = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/about-aemg/intro"
ROBOTS_URL = "https://experienceleague.adobe.com/robots.txt"
# helpx publishes a flat per-locale sitemap (a single <urlset>, NOT a
# sitemap-index of child sitemaps like experienceleague). We fetch this one
# document directly and keep only its in-scope <loc> URLs.
SITEMAP_URL = "https://experienceleague.adobe.com/sitemap.xml"
USER_AGENT = (
    "AEMGuidesExperienceLeagueCorpusBot/1.0 "
    "(+internal RAG test corpus; contact pulgupta@adobe.com)"
)


def _read_topic_text(path: Path) -> str:
    """Read a generated topic, tolerating legacy non-UTF-8 files from older runs."""
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# robots.txt sets no Crawl-delay for our user-agent group, so honor the project
# floor of 5s between requests to reduce server load during bulk corpus builds.
DEFAULT_DELAY_SECONDS = 5.0
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 4
BATCH_LIMIT = 1000  # default per-run conversion stop (overridable via --limit).
DEFAULT_BATCH_SIZE = 50  # URLs popped + processed (then checkpointed) per iteration.
DEFAULT_STATE_DIR = "experienceleague-dita-corpus"
CONVERTER_VERSION = "experienceleague-html-to-dita/2.0"
SOURCE_TYPE = "official-experience-league"
PRODUCT_NAME = "AEM Guides"

# Link targets with these suffixes are assets, not crawlable HTML pages.
SKIP_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".zip", ".gz", ".tar", ".mp4", ".mov", ".webm", ".mp3", ".css",
    ".js", ".json", ".xml", ".txt", ".woff", ".woff2", ".ttf", ".eot",
}

# Max times a single path segment may repeat consecutively before we treat the
# URL as a self-referential crawl trap (e.g. .../support/support/support/...).
# Such traps grow one segment per hop, so capping the run stops the URL from
# ever being enqueued deep enough that its mirrored topics/ path exceeds the OS
# path-length limit and crashes the write.
MAX_REPEATED_PATH_SEGMENTS = 4

# Filesystem limits we defend against when mirroring a URL path under topics/.
# macOS/APFS caps each path component at 255 bytes and the full path near 1024;
# exceeding either raises OSError(ENAMETOOLONG) mid-write. Checked proactively so
# a pathological URL is skipped cleanly instead of aborting the crawl.
MAX_PATH_COMPONENT_BYTES = 255
MAX_TOTAL_PATH_BYTES = 1024

_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = [
    "p", "ul", "ol", "pre", "table", "blockquote", "figure", "img",
    "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "div", "dl",
]
_DROP_TAGS = [
    "script", "style", "nav", "header", "footer", "aside", "form",
    "noscript", "svg", "button", "iframe", "template",
]
# In-page table-of-contents / "On this page" jump-nav blocks. These are NOT
# semantic <nav>/<aside> (those are already in _DROP_TAGS) -- helpx renders the
# in-page TOC as a plain <div>/<ul> carrying a TOC class/role, so it survives
# the _DROP_TAGS pass and leaks into the topic body as a list of anchor links.
# Selectors use the whitespace-token operator [class~=...] and anchored id
# matches so they match the TOC container exactly without false-matching
# content words (e.g. "protocol", "stock").
_TOC_SELECTORS = [
    "[role=navigation]",
    "[role=directory]",
    "[class~=toc]",
    "[class~=mini-toc]",
    "[class~=minitoc]",
    "[class~=on-this-page]",
    "[class~=onthispage]",
    "[class~=table-of-contents]",
    "[class~=in-page-nav]",
    "[class~=page-toc]",
    "[class~=jump-links]",
    "#toc",
    '[id^="toc-"]',
    '[id$="-toc"]',
]
_NOTE_CLASS_KEYWORDS = (
    "danger", "warning", "caution", "important", "attention", "tip", "note",
)


@dataclass(frozen=True)
class FetchResult:
    """Fetched source plus safe provenance metadata used for conversion/indexing."""

    fetched_url: str
    canonical_url: str
    html: str
    content_hash: str
    crawled_at: str
    http_status: int
    etag: str
    last_modified: str
    source_last_updated: str
    language: str
    raw_snapshot: str


# =============================================================================
# Rule-based HTML -> DITA topic converter
# =============================================================================
class DitaTopicConverter:
    """Best-effort, rule-based HTML -> DITA <topic> conversion (no LLM)."""

    def __init__(self) -> None:
        # Per-page base URL for resolving relative <a href> values. Set at the
        # top of convert(); conversion is single-threaded so this is safe.
        self._base_url = ""

    def convert(self, soup: BeautifulSoup, url: str, provenance: Optional[dict] = None) -> str:
        """Return a DITA <topic> XML string for the given parsed page."""
        self._base_url = url
        title = self._extract_title(soup, url)
        shortdesc = self._extract_shortdesc(soup)
        root = self._select_content_root(soup)
        body = self._assemble_body(self._walk(root))
        topic_id = self._topic_id(url)
        shortdesc_xml = f"<shortdesc>{escape(shortdesc)}</shortdesc>" if shortdesc else ""
        prolog_xml = self._prolog_xml(
            {
                "source-type": SOURCE_TYPE,
                "source-url": url,
                "canonical-url": url,
                "product": PRODUCT_NAME,
                "page-title": title,
                "source-language": self._extract_language(soup),
                "converter-version": CONVERTER_VERSION,
                **(provenance or {}),
            }
        )
        return (
            f"{_DITA_PROLOG}"
            f'<topic id={quoteattr(topic_id)}>'
            f"<title>{escape(title)}</title>"
            f"{shortdesc_xml}"
            f"{prolog_xml}"
            f"<body>{body}</body>"
            f"</topic>\n"
        )

    # --- content selection ---------------------------------------------------
    def _select_content_root(self, soup: BeautifulSoup) -> Tag:
        """Pick the main content region and strip boilerplate in place."""
        root: Optional[Tag] = None
        for selector in ["main", "article", "[role=main]", "#content", ".content"]:
            root = soup.select_one(selector)
            if root:
                break
        if root is None:
            root = soup.body or soup
        for tag in root.find_all(_DROP_TAGS):
            tag.decompose()
        self._strip_in_page_toc(root)
        return root

    def _strip_in_page_toc(self, root: Tag) -> None:
        """Remove in-page TOC / jump-nav blocks nested inside the content root.

        Semantic <nav>/<aside> are handled by _DROP_TAGS; this strips the
        non-semantic TOC containers (div/ul carrying a TOC class or nav role)
        that helpx renders inside <main>, so the topic body holds only article
        content and not the "On this page" anchor list.
        """
        for selector in _TOC_SELECTORS:
            for tag in root.select(selector):
                tag.decompose()

    def _extract_title(self, soup: BeautifulSoup, url: str) -> str:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(strip=True)
        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta and meta.get("content", "").strip():
            return meta["content"].strip()
        if soup.title and soup.title.get_text(strip=True):
            return soup.title.get_text(strip=True)
        slug = _slugify(urlparse(url).path) or "untitled"
        return slug.replace("-", " ").title()

    def _extract_shortdesc(self, soup: BeautifulSoup) -> str:
        for attrs in ({"name": "description"}, {"property": "og:description"}):
            meta = soup.find("meta", attrs=attrs)
            if meta and meta.get("content", "").strip():
                return meta["content"].strip()[:500]
        return ""

    def _extract_language(self, soup: BeautifulSoup) -> str:
        html = soup.find("html")
        if html and html.get("lang"):
            return str(html["lang"]).strip()
        meta = soup.find("meta", attrs={"http-equiv": re.compile("^content-language$", re.I)})
        if meta and meta.get("content"):
            return str(meta["content"]).strip()
        return "en"

    def _prolog_xml(self, metadata: dict) -> str:
        rows = []
        for name, value in metadata.items():
            text = str(value or "").strip()
            if not text:
                continue
            rows.append(f'<othermeta name={quoteattr(str(name))} content={quoteattr(text)}/>')
        return f"<prolog><metadata>{''.join(rows)}</metadata></prolog>" if rows else ""

    def _topic_id(self, url: str) -> str:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        return f"t-{digest}"

    # --- block walking -------------------------------------------------------
    def _walk(self, element: Tag) -> List[Tuple]:
        """Walk children, returning ordered ('heading'|'block', ...) items."""
        items: List[Tuple] = []
        for child in element.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    items.append(("block", f"<p>{escape(text)}</p>"))
                continue
            if isinstance(child, Tag):
                self._dispatch_child(child, items)
        return items

    def _dispatch_child(self, child: Tag, items: List[Tuple]) -> None:
        """Route a single element to the correct block builder."""
        name = child.name.lower()
        if name in _DROP_TAGS:
            return
        if name in _HEADINGS:
            title = self._inline(child)
            if title:
                items.append(("heading", int(name[1]), title))
            return
        block = self._element_to_block(child, name)
        if block is not None:
            if block:
                items.append(("block", block))
            return
        if self._has_block_descendant(child):
            items.extend(self._walk(child))
            return
        text = self._inline(child)
        if text:
            items.append(("block", f"<p>{text}</p>"))

    def _element_to_block(self, child: Tag, name: str) -> Optional[str]:
        """Return block XML for a recognized leaf block, else None."""
        if name == "p":
            inner = self._inline(child)
            return f"<p>{inner}</p>" if inner else ""
        if name in ("ul", "ol"):
            return self._list_xml(child)
        if name == "pre":
            return self._codeblock_xml(child)
        if name == "table":
            return self._table_xml(child)
        if name == "blockquote" or self._is_note(child):
            return self._note_xml(child)
        if name in ("figure", "img", "picture"):
            return self._image_xml(child)
        return None

    def _has_block_descendant(self, element: Tag) -> bool:
        return element.find(_BLOCK_TAGS) is not None

    def _is_note(self, element: Tag) -> Optional[str]:
        if element.name.lower() not in ("div", "aside", "section"):
            return None
        classes = " ".join(element.get("class", [])).lower()
        for keyword in _NOTE_CLASS_KEYWORDS:
            if keyword in classes:
                return keyword
        return None

    # --- block builders ------------------------------------------------------
    def _list_xml(self, element: Tag) -> str:
        tag = element.name.lower()
        parts: List[str] = []
        for li in element.find_all("li", recursive=False):
            if self._has_block_descendant(li):
                inner = self._flatten(self._walk(li))
            else:
                inner = self._inline(li)
            parts.append(f"<li>{inner}</li>")
        return f"<{tag}>{''.join(parts)}</{tag}>" if parts else ""

    def _codeblock_xml(self, element: Tag) -> str:
        text = element.get_text()
        return f"<codeblock>{escape(text)}</codeblock>" if text.strip() else ""

    def _table_xml(self, element: Tag) -> str:
        rows = element.find_all("tr")
        head = ""
        body: List[str] = []
        for index, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            entries = "".join(f"<stentry>{self._inline(c)}</stentry>" for c in cells)
            if index == 0 and row.find("th") is not None:
                head = f"<sthead>{entries}</sthead>"
            else:
                body.append(f"<strow>{entries}</strow>")
        if not body and head:
            body = [head.replace("sthead", "strow").replace("stentry", "stentry")]
            head = ""
        if not body:
            return ""
        return f"<simpletable>{head}{''.join(body)}</simpletable>"

    def _note_xml(self, element: Tag) -> str:
        note_type = self._is_note(element) or "note"
        inner = self._flatten(self._walk(element))
        if not inner:
            text = self._inline(element)
            inner = f"<p>{text}</p>" if text else ""
        if not inner:
            return ""
        return f'<note type="{note_type}">{inner}</note>'

    def _image_xml(self, element: Tag) -> str:
        img = element if element.name.lower() == "img" else element.find("img")
        if not img or not img.get("src"):
            return ""
        href = img["src"].strip()
        alt = img.get("alt", "").strip()
        alt_xml = f"<alt>{escape(alt)}</alt>" if alt else ""
        return f"<fig><image href={quoteattr(href)}>{alt_xml}</image></fig>"

    # --- inline + assembly ---------------------------------------------------
    def _inline(self, element: Tag) -> str:
        """Serialize inline content to DITA inline markup."""
        parts: List[str] = []
        for child in element.children:
            if isinstance(child, NavigableString):
                parts.append(escape(str(child)))
                continue
            if not isinstance(child, Tag):
                continue
            parts.append(self._inline_tag(child))
        return "".join(parts).strip()

    def _inline_tag(self, child: Tag) -> str:
        name = child.name.lower()
        if name in ("script", "style"):
            return ""
        if name == "br":
            return " "
        inner = self._inline(child)
        if name == "a":
            return self._anchor_xref(child, inner)
        if name in ("b", "strong"):
            return f"<b>{inner}</b>"
        if name in ("i", "em"):
            return f"<i>{inner}</i>"
        if name in ("code", "tt", "kbd", "samp"):
            return f"<codeph>{inner}</codeph>"
        return inner

    def _anchor_xref(self, child: Tag, inner: str) -> str:
        """Build an xref for an <a>, or drop to plain text when not linkable.

        In-scope links (same domain + /in/ prefix) are emitted as an
        external-shaped placeholder using the canonical absolute URL; a later
        fixup pass localizes them to sibling .dita files once targets exist.
        Out-of-scope http(s) links stay external; fragment-only / mailto: /
        relative-non-http links keep just their text.
        """
        href = child.get("href", "").strip()
        if not href or href.startswith("#"):
            return inner
        absolute = urljoin(self._base_url, href)
        if not absolute.startswith(("http://", "https://")):
            return inner
        canonical = _canonical(absolute)
        target = canonical if (canonical and _in_scope(canonical)) else absolute
        text = inner or escape(target)
        return f'<xref href={quoteattr(target)} scope="external" format="html">{text}</xref>'

    def _flatten(self, items: List[Tuple]) -> str:
        """Flatten walk items into block XML, headings -> bold paragraphs."""
        parts: List[str] = []
        for item in items:
            if item[0] == "heading":
                parts.append(f"<p><b>{item[2]}</b></p>")
            else:
                parts.append(item[1])
        return "".join(parts)

    def _assemble_body(self, items: List[Tuple]) -> str:
        """Split walk items into intro blocks + <section>s at h1/h2 boundaries."""
        intro: List[str] = []
        sections: List[Tuple[str, List[str]]] = []
        current: Optional[Tuple[str, List[str]]] = None
        for item in items:
            if item[0] == "heading" and item[1] == 1:
                continue  # h1 is the topic <title>; don't duplicate as a section.
            if item[0] == "heading" and item[1] == 2:
                current = (item[2], [])
                sections.append(current)
                continue
            if item[0] == "heading":
                target = current[1] if current else intro
                target.append(f"<p><b>{item[2]}</b></p>")
                continue
            target = current[1] if current else intro
            target.append(item[1])
        parts = list(intro)
        for title, blocks in sections:
            title_xml = f"<title>{title}</title>" if title else ""
            parts.append(f"<section>{title_xml}{''.join(blocks)}</section>")
        return "".join(parts)


# =============================================================================
# URL helpers
# =============================================================================
def _canonical(url: str) -> Optional[str]:
    """Normalize a URL: https host, no fragment, no query, no trailing slash."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != HOST:
        return None
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(("https", HOST, path, "", "", ""))


def _canonical_from_soup(soup: BeautifulSoup, fallback_url: str) -> str:
    """Resolve an HTML canonical link, but only trust it inside the approved scope."""
    link = soup.find("link", rel=lambda value: value and "canonical" in str(value).lower())
    href = link.get("href", "").strip() if isinstance(link, Tag) else ""
    if href:
        canonical = _canonical(urljoin(fallback_url, href))
        if canonical and _in_scope(canonical):
            return canonical
    return _canonical(fallback_url) or fallback_url


def _source_last_updated(soup: BeautifulSoup, headers: dict) -> str:
    """Best-effort source date from page metadata, falling back to Last-Modified."""
    meta_names = {
        "last-modified",
        "modified",
        "date",
        "dcterms.modified",
        "article:modified_time",
        "publishdate",
        "published-time",
    }
    for meta in soup.find_all("meta"):
        key = str(meta.get("name") or meta.get("property") or "").strip().lower()
        if key in meta_names and meta.get("content"):
            return str(meta["content"]).strip()
    time_tag = soup.find("time")
    if isinstance(time_tag, Tag):
        value = str(time_tag.get("datetime") or time_tag.get_text(" ", strip=True) or "").strip()
        if value:
            return value
    return str(headers.get("Last-Modified") or headers.get("last-modified") or "").strip()


def _page_language(soup: BeautifulSoup) -> str:
    html = soup.find("html")
    if html and html.get("lang"):
        return str(html["lang"]).strip()
    return "en"


def _in_scope(url: str) -> bool:
    return url.startswith(SCOPE_PREFIX)


def _is_crawlable(url: str) -> bool:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix not in SKIP_EXTENSIONS


def _is_crawl_trap(url: str) -> bool:
    """True if the URL path repeats one segment past MAX_REPEATED_PATH_SEGMENTS
    times in a row (a self-referential link chain like .../support/support/...)."""
    run = 1
    previous = None
    for segment in urlparse(url).path.split("/"):
        if not segment:
            continue
        if segment == previous:
            run += 1
            if run > MAX_REPEATED_PATH_SEGMENTS:
                return True
        else:
            run = 1
            previous = segment
    return False


def _path_within_limits(path: Path) -> bool:
    """True if every component fits NAME_MAX and the whole path fits PATH_MAX."""
    if len(str(path).encode("utf-8")) > MAX_TOTAL_PATH_BYTES:
        return False
    return all(
        len(part.encode("utf-8")) <= MAX_PATH_COMPONENT_BYTES for part in path.parts
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(path: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return slug[:60]


def _pretty_print_dita(dita_xml: str) -> str:
    """Re-indent assembled DITA with 4-space nesting; keep prolog + well-formedness.

    Parses only the <topic> root (lxml would otherwise drop/reformat the DOCTYPE),
    re-indents element-content nodes while leaving mixed inline content (<b>, <xref>
    inside <p>) on one line, then re-prepends the canonical XML declaration + DOCTYPE.
    Falls back to the original string on parse failure so one malformed page never
    aborts a long crawl.
    """
    start = dita_xml.find("<topic")
    if start == -1:
        return dita_xml
    try:
        root = etree.fromstring(dita_xml[start:].encode("utf-8"), _topic_parser())
    except etree.XMLSyntaxError as exc:
        print(f"WARN: pretty-print skipped, writing unformatted ({exc})")
        return dita_xml
    return _serialize_topic(root)


def _topic_parser() -> etree.XMLParser:
    """Parser that strips existing indentation so re-serialization is stable."""
    return etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)


def _serialize_topic(root: etree._Element) -> str:
    """4-space-indent a <topic> root and re-prepend the canonical prolog."""
    etree.indent(root, space=_INDENT)
    body = etree.tostring(root, encoding="unicode")
    if not body.endswith("\n"):
        body += "\n"
    return f"{_DITA_PROLOG}{body}"


# =============================================================================
# Crawler
# =============================================================================
class Crawler:
    """Persistent, resumable, polite crawler for the docs test corpus."""

    def __init__(
        self,
        state_dir: Path,
        batch_size: int = DEFAULT_BATCH_SIZE,
        delay_override: Optional[float] = None,
        limit: int = BATCH_LIMIT,
    ) -> None:
        self._state_dir = state_dir
        self._batch_size = batch_size
        self._delay_override = delay_override
        self._limit = limit
        self._topics_dir = state_dir / "topics"
        self._queue_path = state_dir / "queue.json"
        self._manifest_path = state_dir / "manifest.json"
        self._crawl_state_path = state_dir / "crawl_state.json"
        self._pending_xrefs_path = state_dir / "pending_xrefs.json"
        self._conflicts_path = state_dir / "conflicts.json"
        self._raw_snapshots_dir = state_dir / "raw_snapshots"
        self._queue: Deque[str] = deque()
        self._queued: Set[str] = set()
        self._manifest: Dict[str, str] = {}
        self._crawl_state: Dict[str, dict] = {}
        # Distinct URLs skipped because their clean relpath collided with an
        # already-owned one: {skipped_url: {"path": relpath, "occupied_by": url}}.
        self._conflicts: Dict[str, Dict[str, str]] = {}
        # Relpaths of topics still holding unresolved in-scope xref placeholders.
        # Only these are revisited by the cross-reference fixup pass each run.
        self._pending_xrefs: Set[str] = set()
        # All assigned topic relpaths (mirrors manifest.values()); used to detect
        # clean-filename collisions between distinct URLs.
        self._used_relpaths: Set[str] = set()
        self._visited_this_run: Set[str] = set()
        self._converted_this_run = 0
        self._stop = False
        self._converter = DitaTopicConverter()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        self._robots = self._load_robots()
        if delay_override is not None:
            self._delay = delay_override
        else:
            self._delay = max(DEFAULT_DELAY_SECONDS, self._robots.crawl_delay(USER_AGENT) or 0)

    # --- state persistence ---------------------------------------------------
    def state_exists(self) -> bool:
        return self._manifest_path.exists() or self._queue_path.exists()

    def load(self) -> None:
        if self._queue_path.exists():
            pending = json.loads(self._queue_path.read_text(encoding="utf-8")).get("pending", [])
            self._queue = deque(pending)
            self._queued = set(pending)
        if self._manifest_path.exists():
            self._manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        if self._crawl_state_path.exists():
            self._crawl_state = json.loads(self._crawl_state_path.read_text(encoding="utf-8"))
        if self._pending_xrefs_path.exists():
            self._pending_xrefs = set(json.loads(self._pending_xrefs_path.read_text(encoding="utf-8")))
        if self._conflicts_path.exists():
            self._conflicts = json.loads(self._conflicts_path.read_text(encoding="utf-8"))
        self._used_relpaths = set(self._manifest.values())
        # Self-driving: recompute every relpath under the current scheme and move
        # any that differ. No hardcoded "old scheme looked like X" heuristic, so
        # this handles this rename and any future _topic_relpath change.
        self._migrate_layout()

    def seed(self) -> None:
        self._enqueue(SEED_URL, reason="seed")

    def topup_from_sitemap(self) -> None:
        """Enqueue in-scope sitemap URLs not already known.

        Runs on every invocation (fresh or resumed): fetching a small XML file is
        negligible, and `_enqueue` no-ops on anything already in the queue,
        manifest, or visited-this-run set, so this is cheap and idempotent.
        """
        urls = self._sitemap_urls()
        if not urls:
            return
        before = len(self._queue)
        for url in urls:
            self._enqueue(url, reason="sitemap", discovered_from=SITEMAP_URL)
        added = len(self._queue) - before
        print(f"Sitemap: {len(urls)} in-scope URL(s) listed; {added} new enqueued.")

    def enqueue_known_for_refresh(self) -> None:
        """Queue already-converted URLs for conditional refresh without deleting old output."""
        before = len(self._queue)
        for url in sorted(self._manifest):
            if url in self._queued or url in self._visited_this_run:
                continue
            self._queue.append(url)
            self._queued.add(url)
            self._crawl_state.setdefault(url, {}).update(
                {
                    "canonical_url": url,
                    "discovery_reason": "refresh-known",
                    "queued_at": _utc_now(),
                }
            )
        added = len(self._queue) - before
        print(f"Refresh: {added} known URL(s) enqueued for conditional refresh.")

    def _save(self) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self._queue_path, {"pending": list(self._queue)})
        self._atomic_write(self._manifest_path, self._manifest)
        self._atomic_write(self._crawl_state_path, self._crawl_state)
        self._atomic_write(self._pending_xrefs_path, sorted(self._pending_xrefs))
        self._atomic_write(self._conflicts_path, self._conflicts)

    def _atomic_write(self, path: Path, data: object) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    # --- queue management ----------------------------------------------------
    def _enqueue(self, url: str, reason: str = "link", discovered_from: str = "") -> None:
        canonical = _canonical(url)
        if canonical is None or not _in_scope(canonical) or not _is_crawlable(canonical):
            return
        if _is_crawl_trap(canonical):
            return  # self-referential repeated-segment chain; never crawlable
        if canonical in self._queued or canonical in self._manifest:
            return
        if canonical in self._conflicts:
            return  # known path collision, recorded once; never requeue
        if canonical in self._visited_this_run:
            return
        self._crawl_state.setdefault(canonical, {}).update(
            {
                "canonical_url": canonical,
                "discovery_reason": reason,
                "discovered_from": discovered_from,
                "queued_at": _utc_now(),
            }
        )
        self._queue.append(canonical)
        self._queued.add(canonical)

    # --- robots + fetching ---------------------------------------------------
    def _load_robots(self) -> robotparser.RobotFileParser:
        """Fetch robots.txt with our own session (consistent UA) and parse it.

        robotparser.read() uses urllib with its default user-agent, which the
        site's bot manager handles inconsistently (challenge pages flip the
        parser between allow-all and disallow-all). Fetching via the crawl
        session and feeding parse() the text avoids that flakiness.
        """
        parser = robotparser.RobotFileParser()
        parser.set_url(ROBOTS_URL)
        try:
            response = self._session.get(ROBOTS_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            print(f"WARN: could not fetch robots.txt ({exc}); proceeding with rate limit")
            parser.parse([])
            return parser
        if response.status_code == 200:
            parser.parse(response.text.splitlines())
        else:
            print(f"WARN: robots.txt returned {response.status_code}; proceeding with rate limit")
            parser.parse([])
        return parser

    def _fetch(self, url: str) -> Optional[FetchResult]:
        """Fetch HTML with retry+backoff. Returns None if not usable HTML."""
        previous = self._crawl_state.get(url) or {}
        headers: dict[str, str] = {}
        if previous.get("etag"):
            headers["If-None-Match"] = str(previous["etag"])
        if previous.get("last_modified"):
            headers["If-Modified-Since"] = str(previous["last_modified"])
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._session.get(
                    url,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    headers=headers or None,
                    allow_redirects=True,
                )
            except requests.RequestException as exc:
                self._record_fetch_failure(url, "transient_network_error", str(exc), attempt)
                self._backoff(attempt, f"error {exc}")
                continue
            final_url = _canonical(response.url)
            if not final_url or not _in_scope(final_url):
                self._record_fetch_failure(url, "redirect_out_of_scope", response.url, attempt)
                print(f"SKIP {url} (redirected outside allowed scope: {response.url})")
                return None
            if response.status_code == 304 and previous.get("content_hash"):
                self._crawl_state.setdefault(url, {}).update(
                    {
                        "http_status": 304,
                        "last_checked_at": _utc_now(),
                        "unchanged": True,
                    }
                )
                print(f"UNCHANGED {url} (HTTP 304)")
                return None
            if response.status_code == 200:
                if "text/html" not in response.headers.get("Content-Type", ""):
                    self._record_fetch_failure(url, "unsupported_mime_type", response.headers.get("Content-Type", ""), attempt)
                    return None
                soup = BeautifulSoup(response.text, "lxml")
                canonical_url = _canonical_from_soup(soup, final_url)
                content_hash = "sha256:" + hashlib.sha256(response.content).hexdigest()
                if previous.get("content_hash") == content_hash and url in self._manifest:
                    self._crawl_state.setdefault(url, {}).update(
                        {
                            "canonical_url": canonical_url,
                            "fetched_url": final_url,
                            "http_status": 200,
                            "last_checked_at": _utc_now(),
                            "unchanged": True,
                        }
                    )
                    print(f"UNCHANGED {url} (content hash match)")
                    return None
                raw_snapshot = self._write_raw_snapshot(content_hash, response.text)
                return FetchResult(
                    fetched_url=final_url,
                    canonical_url=canonical_url,
                    html=response.text,
                    content_hash=content_hash,
                    crawled_at=_utc_now(),
                    http_status=response.status_code,
                    etag=str(response.headers.get("ETag") or response.headers.get("etag") or ""),
                    last_modified=str(response.headers.get("Last-Modified") or response.headers.get("last-modified") or ""),
                    source_last_updated=_source_last_updated(soup, response.headers),
                    language=_page_language(soup),
                    raw_snapshot=raw_snapshot,
                )
            if response.status_code in (429, 500, 502, 503, 504):
                failure_type = "rate_limit" if response.status_code == 429 else "transient_http_error"
                self._record_fetch_failure(url, failure_type, str(response.status_code), attempt)
                self._backoff(attempt, f"status {response.status_code}")
                continue
            if response.status_code in (401, 403):
                self._record_fetch_failure(url, "authorization_failure", str(response.status_code), attempt)
                print(f"SKIP {url} (status {response.status_code})")
                return None
            if response.status_code == 404:
                self._record_fetch_failure(url, "not_found_or_deleted", str(response.status_code), attempt)
                print(f"SKIP {url} (status {response.status_code})")
                return None
            print(f"SKIP {url} (status {response.status_code})")
            self._record_fetch_failure(url, "http_error", str(response.status_code), attempt)
            return None
        print(f"GIVEUP {url} (exhausted {MAX_RETRIES} retries)")
        self._record_fetch_failure(url, "retry_exhausted", f"{MAX_RETRIES} attempts", MAX_RETRIES)
        return None

    def _record_fetch_failure(self, url: str, failure_type: str, detail: str, attempt: int) -> None:
        state = self._crawl_state.setdefault(url, {"canonical_url": url})
        state.update(
            {
                "last_failure_type": failure_type,
                "last_failure_detail": detail[:500],
                "last_failure_at": _utc_now(),
                "retry_count": int(state.get("retry_count") or 0) + 1,
                "last_attempt": attempt,
            }
        )

    def _write_raw_snapshot(self, content_hash: str, html: str) -> str:
        digest = content_hash.split(":", 1)[-1]
        shard = digest[:2]
        path = self._raw_snapshots_dir / shard / f"{digest}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(html, encoding="utf-8")
        return str(path.relative_to(self._state_dir))

    def _backoff(self, attempt: int, reason: str) -> None:
        wait = min(2 ** attempt, 30) + random.uniform(0, 1)
        print(f"retry {attempt}/{MAX_RETRIES} in {wait:.1f}s ({reason})")
        time.sleep(wait)

    def _sitemap_urls(self) -> List[str]:
        """Discover in-scope page URLs from the flat per-locale sitemap.

        Experience League sitemap behavior can vary; we fetch the configured sitemap, extract its <loc> values, and keep only canonicalized in-scope page URLs. Best-effort:
        any fetch/parse failure just contributes nothing.
        """
        urls: Set[str] = set()
        for loc in self._fetch_sitemap_locs(SITEMAP_URL):
            canonical = _canonical(loc)
            if canonical and _in_scope(canonical):
                urls.add(canonical)
        return sorted(urls)

    def _fetch_sitemap_locs(self, url: str) -> List[str]:
        """Fetch one XML sitemap and return its <loc> values ([] on any failure)."""
        try:
            response = self._session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException:
            return []
        if response.status_code != 200:
            return []
        return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", response.text)

    # --- conversion + output -------------------------------------------------
    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> None:
        for anchor in soup.find_all("a", href=True):
            self._enqueue(urljoin(base_url, anchor["href"]), reason="page-link", discovered_from=base_url)

    def _topic_relpath(self, url: str) -> Path:
        """Assign a topic relpath: clean URL-mirrored path, hashed only on collision.

        Returns the hash-free `topics/<url-path-dirs>/<last-segment>.dita` unless
        that clean path is already assigned to a *different* URL (checked against
        the used-paths registry, not the filesystem), in which case an 8-char hash
        disambiguator is appended so two distinct URLs never share a file. Only
        called for URLs not yet in the registry.
        """
        clean = self._clean_relpath(url)
        if str(clean) not in self._used_relpaths:
            return clean
        return self._hashed_relpath(url)

    def _url_segments(self, url: str) -> List[str]:
        """Slug-sanitized URL path segments (split on '/'; empties/dots dropped).

        Splitting on '/' only keeps a hyphenated segment like 'core-services' as
        one directory; '.'/'..'/empty collapse to nothing, so no path traversal.
        """
        return [s for s in (_slugify(seg) for seg in urlparse(url).path.split("/")) if s]

    def _clean_relpath(self, url: str) -> Path:
        """Hash-free relpath: topics/<dirs>/<last-segment>.dita."""
        segments = self._url_segments(url)
        if not segments:
            return Path("topics") / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]}.dita"
        *dirs, last = segments
        return Path("topics", *dirs, f"{last}.dita")

    def _hashed_relpath(self, url: str) -> Path:
        """Disambiguated relpath: topics/<dirs>/<last-segment>-<hash>.dita."""
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        segments = self._url_segments(url)
        if not segments:
            return Path("topics") / f"{digest}.dita"
        *dirs, last = segments
        return Path("topics", *dirs, f"{last}-{digest}.dita")

    def _write_topic(self, url: str, dita_xml: str) -> Optional[str]:
        """Write the topic file and return its relpath, or None if unwritable.

        Returns None (caller skips the URL) when the mirrored path exceeds the
        OS length limit -- checked proactively, with an OSError backstop for any
        limit we didn't anticipate -- so one pathological URL never aborts the
        crawl and the URL is left out of the manifest since nothing was written.
        """
        relpath = self._topic_relpath(url)
        out_path = self._state_dir / relpath
        if not _path_within_limits(out_path):
            print(f"SKIP {url} (path too long: {relpath}); not written")
            return None
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(_pretty_print_dita(dita_xml), encoding="utf-8")
        except OSError as exc:
            print(f"SKIP {url} (write failed on {relpath}: {exc}); not written")
            return None
        return str(relpath)

    # --- self-driving layout migration --------------------------------------
    def _migrate_layout(self) -> None:
        """Re-derive every topic's relpath under the current scheme and move any
        that changed.

        Self-driving: recomputes `_topic_relpath(url)` for the whole manifest and
        migrates entries whose stored path differs, so it adapts to any scheme
        change (not a hardcoded old-layout check). Moves files, rewrites manifest
        + pending_xrefs, and recomputes already-localized (scope="local") xrefs so
        links survive the move. Collision-aware: assignments are rebuilt in a
        deterministic (sorted) order, so two URLs whose clean names collide are
        disambiguated the same way every run. Idempotent: manifest.json is written
        only at the end, so a crashed run replays cleanly.
        """
        old_manifest = dict(self._manifest)
        new_manifest = self._reassign_relpaths(old_manifest)
        moved = {url for url in old_manifest if old_manifest[url] != new_manifest[url]}
        if not moved:
            self._manifest = new_manifest
            return
        print(f"Migrating layout: {len(moved)} topic(s) to the current path scheme...")
        old_rel_to_new = {old_manifest[url]: new_manifest[url] for url in old_manifest}
        for url in moved:
            self._move_topic_file(old_manifest[url], new_manifest[url])
        self._manifest = new_manifest
        self._pending_xrefs = {old_rel_to_new.get(rel, rel) for rel in self._pending_xrefs}
        for url in old_manifest:
            self._relink_after_move(new_manifest[url], old_manifest[url], old_rel_to_new)
        self._prune_empty_topic_dirs()
        self._save()
        print("Layout migration complete.")

    def _reassign_relpaths(self, manifest: Dict[str, str]) -> Dict[str, str]:
        """Rebuild url -> relpath deterministically, disambiguating collisions.

        Processes URLs sorted so the first URL to claim a clean name keeps it and
        later colliders get the hashed name, identically on every run.
        """
        self._used_relpaths = set()
        new_manifest: Dict[str, str] = {}
        for url in sorted(manifest):
            relpath = str(self._topic_relpath(url))
            new_manifest[url] = relpath
            self._used_relpaths.add(relpath)
        return new_manifest

    def _move_topic_file(self, old_rel: str, new_rel: str) -> None:
        old_path = self._state_dir / old_rel
        new_path = self._state_dir / new_rel
        if not old_path.exists():
            if not new_path.exists():
                print(f"WARN: migration source missing, cannot move {old_rel}")
            return  # already moved (re-run) or genuinely gone
        new_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(old_path, new_path)

    def _relink_after_move(self, new_rel: str, old_rel: str, old_rel_to_new: Dict[str, str]) -> None:
        """Recompute a moved file's local xrefs against the new target paths."""
        path = self._state_dir / new_rel
        text = _read_topic_text(path)
        if 'scope="local"' not in text:
            return
        start = text.find("<topic")
        if start == -1:
            return
        try:
            root = etree.fromstring(text[start:].encode("utf-8"), _topic_parser())
        except etree.XMLSyntaxError:
            return
        changed = self._rewrite_local_hrefs(root, old_rel, new_rel, old_rel_to_new)
        if changed:
            path.write_text(_serialize_topic(root), encoding="utf-8")

    def _rewrite_local_hrefs(
        self, root: etree._Element, old_rel: str, new_rel: str, old_rel_to_new: Dict[str, str]
    ) -> int:
        """Translate each local xref's old relative href to the new layout. Returns count."""
        old_dir = str(Path(old_rel).parent)
        new_dir = str(Path(new_rel).parent)
        changed = 0
        for xref in root.iter("xref"):
            if xref.get("scope") != "local":
                continue
            old_href = xref.get("href", "")
            old_target = os.path.normpath(os.path.join(old_dir, old_href))
            new_target = old_rel_to_new.get(old_target)
            if not new_target:
                continue  # already new-scheme (re-run) or unknown target -> leave as is
            new_href = Path(os.path.relpath(new_target, start=new_dir)).as_posix()
            if new_href != old_href:
                xref.set("href", new_href)
                changed += 1
        return changed

    def _prune_empty_topic_dirs(self) -> None:
        if not self._topics_dir.exists():
            return
        for dirpath, _dirnames, _filenames in os.walk(self._topics_dir, topdown=False):
            path = Path(dirpath)
            if path == self._topics_dir:
                continue
            try:
                path.rmdir()  # succeeds only if now empty
            except OSError:
                pass

    # --- cross-reference fixup ----------------------------------------------
    def _resolve_cross_references(self) -> None:
        """Localize in-scope xref placeholders to sibling .dita files.

        Runs after the crawl loop so the corpus is maximally resolved with
        whatever is in the manifest so far. Only revisits files still holding
        unresolved placeholders (the `_pending_xrefs` set), so cost is
        proportional to unresolved links, not to total corpus size. A file
        drops out of the set once none of its in-scope links remain unresolved.
        """
        resolved_files = 0
        resolved_links = 0
        for relpath in sorted(self._pending_xrefs):
            if self._stop:
                break
            path = self._state_dir / relpath
            if not path.exists():
                self._pending_xrefs.discard(relpath)
                continue
            text = _read_topic_text(path)
            if _INSCOPE_XREF_MARKER not in text:
                self._pending_xrefs.discard(relpath)
                continue
            changed, still_pending = self._localize_file(path, relpath, text)
            if changed:
                resolved_files += 1
                resolved_links += changed
            if not still_pending:
                self._pending_xrefs.discard(relpath)
        self._save()
        if resolved_files:
            print(
                f"Cross-reference fixup: localized {resolved_links} link(s) across "
                f"{resolved_files} file(s); {len(self._pending_xrefs)} file(s) still pending."
            )

    def _localize_file(self, path: Path, relpath: str, text: str) -> Tuple[int, bool]:
        """Rewrite resolvable xrefs in one file. Returns (num_resolved, still_pending)."""
        start = text.find("<topic")
        if start == -1:
            return 0, False
        try:
            root = etree.fromstring(text[start:].encode("utf-8"), _topic_parser())
        except etree.XMLSyntaxError:
            return 0, True
        changed = self._localize_xrefs(root, relpath)
        new_text = _serialize_topic(root) if changed else text
        if changed:
            path.write_text(new_text, encoding="utf-8")
        return changed, (_INSCOPE_XREF_MARKER in new_text)

    def _localize_xrefs(self, root: etree._Element, relpath: str) -> int:
        """Point in-scope external xrefs at sibling .dita files. Returns count."""
        source_dir = str(Path(relpath).parent)
        changed = 0
        for xref in root.iter("xref"):
            if xref.get("scope") != "external":
                continue
            canonical = _canonical(xref.get("href", ""))
            if not canonical or not _in_scope(canonical):
                continue
            target_relpath = self._manifest.get(canonical)
            if not target_relpath:
                continue
            href = Path(os.path.relpath(target_relpath, start=source_dir)).as_posix()
            xref.set("href", href)
            xref.set("scope", "local")
            xref.set("format", "dita")
            changed += 1
        return changed

    # --- main loop -----------------------------------------------------------
    def run(self) -> None:
        self._install_signal_handlers()
        try:
            self._loop()
        finally:
            self._save()
        self._resolve_cross_references()
        self._report()

    def _loop(self) -> None:
        while self._queue and self._converted_this_run < self._limit and not self._stop:
            for url in self._pop_batch():
                if self._converted_this_run >= self._limit or self._stop:
                    break
                self._process(url)
            self._save()

    def _pop_batch(self) -> List[str]:
        """Pop up to batch_size URLs off the queue and mark them visited."""
        batch: List[str] = []
        while self._queue and len(batch) < self._batch_size:
            url = self._queue.popleft()
            self._queued.discard(url)
            self._visited_this_run.add(url)
            batch.append(url)
        return batch

    def _url_for_relpath(self, relpath: str) -> str:
        """Reverse-lookup the URL currently occupying a relpath (for collision logs)."""
        for known_url, known_rel in self._manifest.items():
            if known_rel == relpath:
                return known_url
        return "<unknown>"

    def _process(self, url: str) -> None:
        existing_relpath = self._manifest.get(url)
        clean = str(self._clean_relpath(url))
        if not existing_relpath and clean in self._used_relpaths:
            if url not in self._conflicts:
                occupier = self._url_for_relpath(clean)
                self._conflicts[url] = {"path": clean, "occupied_by": occupier}
                print(
                    f"SKIP {url} (path collision on {clean}, already owned by {occupier}); "
                    "not fetched"
                )
            return
        if not self._robots.can_fetch(USER_AGENT, url):
            print(f"DISALLOWED {url} (robots.txt)")
            self._record_fetch_failure(url, "robots_disallowed", "robots.txt", 0)
            return
        time.sleep(self._delay)
        fetched = self._fetch(url)
        if fetched is None:
            return
        soup = BeautifulSoup(fetched.html, "lxml")
        self._extract_links(soup, url)
        dita_xml = self._converter.convert(
            soup,
            url,
            provenance={
                "source-url": url,
                "canonical-url": fetched.canonical_url,
                "source-last-updated": fetched.source_last_updated,
                "crawled-at": fetched.crawled_at,
                "source-language": fetched.language,
                "content-hash": fetched.content_hash,
                "raw-snapshot": fetched.raw_snapshot,
                "http-etag": fetched.etag,
                "http-last-modified": fetched.last_modified,
            },
        )
        relpath = self._write_topic(url, dita_xml)
        if relpath is None:
            self._record_fetch_failure(url, "write_failure", "topic path not writable", 0)
            return  # unwritable path already logged; leave URL out of the manifest
        self._manifest[url] = relpath
        self._used_relpaths.add(relpath)
        self._crawl_state.setdefault(url, {}).update(
            {
                "canonical_url": fetched.canonical_url,
                "fetched_url": fetched.fetched_url,
                "http_status": fetched.http_status,
                "etag": fetched.etag,
                "last_modified": fetched.last_modified,
                "source_last_updated": fetched.source_last_updated,
                "content_hash": fetched.content_hash,
                "raw_snapshot": fetched.raw_snapshot,
                "topic_relpath": relpath,
                "last_successful_crawl": fetched.crawled_at,
                "last_checked_at": fetched.crawled_at,
                "parser_version": CONVERTER_VERSION,
                "converter_version": CONVERTER_VERSION,
                "source_language": fetched.language,
                "unchanged": False,
            }
        )
        if _INSCOPE_XREF_MARKER in dita_xml:
            self._pending_xrefs.add(relpath)
        self._converted_this_run += 1
        print(f"[{self._converted_this_run}/{self._limit}] {url} -> {relpath}")

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._on_signal)

    def _on_signal(self, signum: int, _frame) -> None:
        print(f"\nreceived signal {signum}; finishing current item and checkpointing")
        self._stop = True

    def _report(self) -> None:
        reason = "per-run limit reached" if self._converted_this_run >= self._limit else (
            "queue empty" if not self._queue else "stopped"
        )
        print(
            f"\nDone ({reason}). Converted this run: {self._converted_this_run}. "
            f"Total converted: {len(self._manifest)}. Queue remaining: {len(self._queue)}."
        )
        if self._converted_this_run >= self._limit:
            print("Review this batch, then re-run with --resume to continue.")


# =============================================================================
# CLI
# =============================================================================
def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="continue from saved state")
    parser.add_argument("--reset", action="store_true", help="wipe state and start fresh")
    parser.add_argument(
        "--refresh-known",
        action="store_true",
        help=(
            "when resuming, conditionally re-check URLs already in manifest using "
            "ETag/Last-Modified/content hash; old valid DITA remains on failures"
        ),
    )
    parser.add_argument(
        "--state-dir",
        default=DEFAULT_STATE_DIR,
        help=f"where queue/manifest/topics live (default: {DEFAULT_STATE_DIR})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=BATCH_LIMIT,
        help=(
            "max topics to convert this run before stopping for review "
            f"(default: {BATCH_LIMIT}); separate from --batch-size"
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=(
            "URLs popped + processed per iteration before checkpointing "
            f"(default: {DEFAULT_BATCH_SIZE}); checkpoint granularity only, "
            "independent of the --limit per-run stop"
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help=(
            "override the per-request sleep (seconds), consciously bypassing "
            f"robots.txt's advisory Crawl-delay; when omitted, uses "
            f"max({DEFAULT_DELAY_SECONDS}, robots crawl-delay). Use for small test runs only"
        ),
    )
    parser.add_argument(
        "--scope-prefix",
        default=SCOPE_PREFIX,
        help=(
            "crawl boundary prefix; default is AEM Guides docs. "
            "Use https://experienceleague.adobe.com/en/docs/ only if you intentionally want a broader Experience League crawl"
        ),
    )
    parser.add_argument("--seed-url", default=SEED_URL, help="first URL to enqueue for a fresh crawl")
    parser.add_argument("--sitemap-url", default=SITEMAP_URL, help="sitemap URL used to top up the queue")
    return parser.parse_args(argv)


def _reset_state(state_dir: Path) -> None:
    import shutil

    if state_dir.exists():
        shutil.rmtree(state_dir)
    print(f"Reset: removed {state_dir}")


def main(argv: List[str]) -> int:
    args = _parse_args(argv)
    global SCOPE_PREFIX, _INSCOPE_XREF_MARKER, SEED_URL, SITEMAP_URL
    SCOPE_PREFIX = args.scope_prefix.rstrip("/") + "/"
    _INSCOPE_XREF_MARKER = '<xref href="' + SCOPE_PREFIX
    SEED_URL = args.seed_url
    SITEMAP_URL = args.sitemap_url

    state_dir = Path(args.state_dir)
    if args.reset:
        _reset_state(state_dir)
    if args.batch_size < 1:
        print("--batch-size must be >= 1")
        return 1
    if args.limit < 1:
        print("--limit must be >= 1")
        return 1
    if args.delay is not None and args.delay < 0:
        print("--delay must be >= 0")
        return 1

    crawler = Crawler(
        state_dir,
        batch_size=args.batch_size,
        delay_override=args.delay,
        limit=args.limit,
    )
    has_state = crawler.state_exists()

    if args.resume:
        if not has_state:
            print("Nothing to resume: no saved state. Run without --resume to start fresh.")
            return 1
        crawler.load()
    elif has_state:
        print(
            "State already exists. Pass --resume to continue, or --reset to start over."
        )
        return 1
    else:
        crawler.seed()

    if args.refresh_known:
        if not args.resume:
            print("--refresh-known requires --resume so existing manifest state is loaded")
            return 1
        crawler.enqueue_known_for_refresh()
    crawler.topup_from_sitemap()  # every invocation: fresh or resumed
    crawler.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
