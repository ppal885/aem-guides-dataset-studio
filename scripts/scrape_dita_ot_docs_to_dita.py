#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scrape DITA-OT official docs into DITA topics for RAG indexing.

The crawler is intentionally scoped to the DITA-OT documentation site and writes
UTF-8 DITA topics with source metadata, a manifest, and a DITA map. It is safe to
run in batches with --limit and resume later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from lxml import etree


DEFAULT_BASE_URL = "https://www.dita-ot.org"
DEFAULT_SCOPE_PREFIX = "https://www.dita-ot.org/dev/"
DEFAULT_SEED_URL = "https://www.dita-ot.org/dev/"
DEFAULT_STATE_DIR = "dita-ot-docs-corpus"
DEFAULT_USER_AGENT = "aem-guides-dataset-studio/1.0 (+DITA-OT docs RAG corpus)"
DEFAULT_LIMIT = 250
DEFAULT_DELAY_SECONDS = 0.5
DITA_PROLOG = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
)
INVALID_XML_CHARS = re.compile(
    "[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]"
)


@dataclass(frozen=True)
class PageResult:
    url: str
    title: str
    shortdesc: str
    topic_xml: str
    links: list[str]
    content_hash: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path(DEFAULT_STATE_DIR))
    parser.add_argument("--seed-url", default=DEFAULT_SEED_URL)
    parser.add_argument("--scope-prefix", default=DEFAULT_SCOPE_PREFIX)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--refresh-known", action="store_true")
    parser.add_argument("--map-name", default="dita-ot-docs.ditamap")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.limit < 1:
        raise SystemExit("--limit must be >= 1")
    if args.delay < 0:
        raise SystemExit("--delay must be >= 0")
    crawler = DitaOtDocsCrawler(args)
    crawler.run()
    return 0


class DitaOtDocsCrawler:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.state_dir = args.state_dir
        self.topics_dir = self.state_dir / "topics"
        self.queue_path = self.state_dir / "queue.json"
        self.seen_path = self.state_dir / "seen.json"
        self.manifest_path = self.state_dir / "manifest.json"
        self.scope_prefix = normalize_scope(args.scope_prefix)
        self.base_url = args.base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": args.user_agent})
        self.robots = load_robots(self.base_url, self.session, args.user_agent)
        self.queue: deque[str] = deque()
        self.seen: set[str] = set()
        self.manifest: dict[str, dict[str, Any]] = {}

    def run(self) -> None:
        if self.args.reset and self.state_dir.exists():
            import shutil

            shutil.rmtree(self.state_dir)
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        if self.args.resume:
            self.load_state()
        elif self.state_exists():
            raise SystemExit("State already exists. Use --resume or --reset.")
        else:
            self.enqueue(self.args.seed_url)
        if self.args.refresh_known:
            self.queue.extend(sorted(self.manifest))
        converted = 0
        while self.queue and converted < self.args.limit:
            url = self.queue.popleft()
            if url in self.seen and not self.args.refresh_known:
                continue
            self.seen.add(url)
            if not self.in_scope(url):
                continue
            if not self.robots.can_fetch(self.args.user_agent, url):
                continue
            try:
                page = self.fetch_page(url)
            except Exception as exc:
                self.manifest[url] = {
                    "url": url,
                    "status": "failed",
                    "error": str(exc),
                }
                self.save_state()
                continue
            relpath = self.write_topic(page)
            self.manifest[url] = {
                "url": url,
                "status": "ok",
                "title": page.title,
                "shortdesc": page.shortdesc,
                "dita_file": relpath,
                "source_url": page.url,
                "canonical_url": page.url,
                "content_hash": page.content_hash,
            }
            for link in page.links:
                self.enqueue(link)
            converted += 1
            print(f"[{converted}/{self.args.limit}] {url} -> {relpath}", flush=True)
            self.save_state()
            time.sleep(self.args.delay)
        self.write_map()
        self.save_state()
        print(
            json.dumps(
                {
                    "converted_this_run": converted,
                    "manifest_total": len([v for v in self.manifest.values() if v.get("status") == "ok"]),
                    "queue_remaining": len(self.queue),
                    "state_dir": str(self.state_dir),
                    "map": str(self.state_dir / self.args.map_name),
                },
                indent=2,
            )
        )

    def state_exists(self) -> bool:
        return self.queue_path.exists() or self.manifest_path.exists()

    def load_state(self) -> None:
        if self.queue_path.exists():
            self.queue = deque(json.loads(self.queue_path.read_text(encoding="utf-8")))
        if self.seen_path.exists():
            self.seen = set(json.loads(self.seen_path.read_text(encoding="utf-8")))
        if self.manifest_path.exists():
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not self.queue and not self.manifest:
            raise SystemExit("Nothing to resume: no saved state.")

    def save_state(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(json.dumps(list(self.queue), indent=2) + "\n", encoding="utf-8")
        self.seen_path.write_text(json.dumps(sorted(self.seen), indent=2) + "\n", encoding="utf-8")
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def enqueue(self, url: str) -> None:
        normalized = normalize_url(urljoin(self.base_url + "/", url))
        if normalized and self.in_scope(normalized) and normalized not in self.seen and normalized not in self.queue:
            self.queue.append(normalized)

    def in_scope(self, url: str) -> bool:
        normalized = normalize_url(url)
        return normalized == self.scope_prefix.rstrip("/") or normalized.startswith(self.scope_prefix)

    def fetch_page(self, url: str) -> PageResult:
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type:
            raise ValueError(f"non-html content-type: {content_type}")
        soup = BeautifulSoup(response.text, "html.parser")
        canonical = canonical_url(soup, url)
        article = soup.find("article") or soup.find("main") or soup.body
        if article is None:
            raise ValueError("no article/main/body content found")
        cleanup_article(article)
        title = page_title(soup, article, canonical)
        shortdesc = first_paragraph(article)
        body = article_to_dita_body(article)
        if not body.strip():
            raise ValueError("no convertible article content found")
        topic_id = safe_id(Path(urlparse(canonical).path).stem or "dita-ot-doc")
        topic_xml = build_topic_xml(topic_id, title, shortdesc, body, canonical)
        validate_topic(topic_xml)
        links = discover_links(soup, canonical, self.scope_prefix, self.base_url)
        digest = "sha256:" + hashlib.sha256(topic_xml.encode("utf-8")).hexdigest()
        return PageResult(canonical, title, shortdesc, topic_xml, links, digest)

    def write_topic(self, page: PageResult) -> str:
        rel = topic_relpath(page.url, self.scope_prefix)
        out_path = self.topics_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(page.topic_xml, encoding="utf-8", newline="\n")
        return f"topics/{rel.as_posix()}"

    def write_map(self) -> None:
        entries = [v for v in self.manifest.values() if v.get("status") == "ok" and v.get("dita_file")]
        entries.sort(key=lambda item: str(item.get("dita_file")))
        topicrefs = "\n".join(
            f'  <topicref href="{escape(str(item["dita_file"]))}" navtitle="{escape(str(item.get("title") or ""))}"/>'
            for item in entries
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
            '<map id="dita-ot-docs-corpus">\n'
            '  <title>DITA-OT official docs corpus</title>\n'
            f"{topicrefs}\n"
            "</map>\n"
        )
        (self.state_dir / self.args.map_name).write_text(xml, encoding="utf-8", newline="\n")


def load_robots(base_url: str, session: requests.Session, user_agent: str) -> RobotFileParser:
    parser = RobotFileParser()
    robots_url = base_url.rstrip("/") + "/robots.txt"
    try:
        response = session.get(robots_url, timeout=15)
        if response.ok:
            parser.parse(response.text.splitlines())
        else:
            parser.parse(["User-agent: *", "Allow: /"])
    except requests.RequestException:
        parser.parse(["User-agent: *", "Allow: /"])
    return parser


def cleanup_article(article: Tag) -> None:
    for selector in ("nav", "script", "style", "aside", "form", ".breadcrumb", ".edit-page", ".pagination"):
        for node in article.select(selector):
            node.decompose()


def page_title(soup: BeautifulSoup, article: Tag, url: str) -> str:
    for candidate in (article.find("h1"), soup.find("h1"), soup.find("title")):
        text = clean_text(candidate.get_text(" ", strip=True) if candidate else "")
        if text:
            return text
    return Path(urlparse(url).path).stem.replace("-", " ").title() or "DITA-OT documentation"


def first_paragraph(article: Tag) -> str:
    paragraph = article.find("p")
    return clean_text(paragraph.get_text(" ", strip=True) if paragraph else "")


def article_to_dita_body(article: Tag) -> str:
    parts: list[str] = []
    for child in article.children:
        parts.extend(convert_node(child, current_level=0))
    return "\n".join(part for part in parts if part.strip())


def convert_node(node: Tag | NavigableString, current_level: int) -> list[str]:
    if isinstance(node, NavigableString):
        text = clean_text(str(node))
        return [f"<p>{escape(text)}</p>"] if text and current_level == 0 else []
    if not isinstance(node, Tag):
        return []
    name = node.name.lower()
    if name in {"h1"}:
        return []
    if name in {"h2", "h3", "h4", "h5", "h6"}:
        title = clean_text(node.get_text(" ", strip=True))
        return [f'<section id="{safe_id(title)}"><title>{escape(title)}</title></section>'] if title else []
    if name == "p":
        text = inline_text(node)
        return [f"<p>{text}</p>"] if text.strip() else []
    if name in {"pre"}:
        text = clean_code(node.get_text("\n"))
        return [f"<codeblock>{escape(text)}</codeblock>"] if text.strip() else []
    if name == "code":
        text = clean_code(node.get_text())
        return [f"<codeblock>{escape(text)}</codeblock>"] if text.strip() and current_level == 0 else []
    if name in {"ul", "ol"}:
        items = []
        for li in node.find_all("li", recursive=False):
            text = inline_text(li)
            if text.strip():
                items.append(f"<li>{text}</li>")
        if not items:
            return []
        tag = "ol" if name == "ol" else "ul"
        return [f"<{tag}>" + "".join(items) + f"</{tag}>"]
    if name == "table":
        rows = []
        for tr in node.find_all("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
            if cells:
                rows.append(" | ".join(cells))
        return [f"<p>{escape('; '.join(rows[:20]))}</p>"] if rows else []
    if name in {"div", "section", "article", "main", "blockquote"}:
        out: list[str] = []
        for child in node.children:
            converted = convert_node(child, current_level + 1)
            out.extend(converted)
        return out
    return [item for child in node.children for item in convert_node(child, current_level + 1)]


def inline_text(node: Tag) -> str:
    chunks: list[str] = []
    for child in node.descendants:
        if isinstance(child, NavigableString):
            text = clean_text(str(child))
            if text:
                chunks.append(escape(text))
        elif isinstance(child, Tag) and child.name and child.name.lower() == "br":
            chunks.append(" ")
    return clean_text(" ".join(chunks))


def build_topic_xml(topic_id: str, title: str, shortdesc: str, body: str, source_url: str) -> str:
    shortdesc_xml = f"  <shortdesc>{escape(shortdesc)}</shortdesc>\n" if shortdesc else ""
    return (
        DITA_PROLOG
        +
        f'<topic id="{escape(topic_id)}" xml:lang="en-US">\n'
        f"  <title>{escape(title)}</title>\n"
        f"{shortdesc_xml}"
        "  <prolog>\n"
        "    <metadata>\n"
        f'      <othermeta name="source-url" content="{escape(source_url)}"/>\n'
        f'      <othermeta name="canonical-url" content="{escape(source_url)}"/>\n'
        '      <othermeta name="source-product-family" content="dita-ot"/>\n'
        '      <othermeta name="source-type" content="official-docs"/>\n'
        "    </metadata>\n"
        "  </prolog>\n"
        "  <body>\n"
        f"{indent_body(body)}\n"
        "  </body>\n"
        "</topic>\n"
    )


def discover_links(soup: BeautifulSoup, page_url: str, scope_prefix: str, base_url: str) -> list[str]:
    out: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        resolved = normalize_url(urljoin(page_url, href))
        if resolved.startswith(scope_prefix) and resolved not in out:
            out.append(resolved)
    return out


def canonical_url(soup: BeautifulSoup, fallback: str) -> str:
    link = soup.find("link", rel=lambda value: value and "canonical" in value)
    if link and link.get("href"):
        return normalize_url(urljoin(fallback, str(link["href"])))
    return normalize_url(fallback)


def topic_relpath(url: str, scope_prefix: str) -> Path:
    normalized = normalize_url(url)
    rel_url = normalized.removeprefix(scope_prefix).strip("/")
    if rel_url == normalized:
        rel_url = normalized.removeprefix(scope_prefix.rstrip("/")).strip("/")
    if not rel_url:
        rel_url = "index"
    parts = [safe_filename(part) for part in rel_url.split("/") if part]
    if not parts:
        parts = ["index"]
    parts[-1] = parts[-1] + ".dita"
    return Path(*parts)


def validate_topic(xml: str) -> None:
    text = re.sub(r"<!DOCTYPE[^>]+>\s*", "", xml)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    etree.fromstring(text.encode("utf-8"), parser)


def normalize_scope(value: str) -> str:
    normalized = normalize_url(value)
    return normalized if normalized.endswith("/") else normalized + "/"


def normalize_url(value: str) -> str:
    value, _fragment = urldefrag(value)
    parsed = urlparse(value)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "www.dita-ot.org"
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return parsed._replace(scheme=scheme, netloc=netloc, path=path, query="").geturl()


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    if not cleaned:
        cleaned = "dita-ot-doc"
    if not re.match(r"^[A-Za-z_]", cleaned):
        cleaned = "id-" + cleaned
    return cleaned[:96]


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return (cleaned or "index")[:120]


def clean_text(value: str) -> str:
    return INVALID_XML_CHARS.sub("", re.sub(r"\s+", " ", value or "")).strip()


def clean_code(value: str) -> str:
    return INVALID_XML_CHARS.sub("", value or "").strip("\n")


def indent_body(body: str) -> str:
    return "\n".join("    " + line if line.strip() else line for line in body.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
