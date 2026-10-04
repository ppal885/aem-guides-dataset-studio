"""Fetch the wiki pages a Jira ticket links to (design documents, specs) so the UAC can be written from them.

The Copilot session cannot open wiki.corp.adobe.com: the page redirects to a login. The runner therefore
fetches every linked page itself with a Confluence personal access token (WIKI_PAT in the env file), writes
the page text into <ticket>/linked-docs/, and lists every link in LINKED_DOCS.json:

    [{"url": "...", "page_id": "4066975661", "status": "READ", "title": "...", "file": "/abs/path.md"},
     {"url": "...", "status": "UNREADABLE", "reason": "WIKI_PAT is not set"}]

Links are taken from the description and from comments not written by the automation.
"""
from __future__ import annotations

import html
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

LINKED_DOCS_FILE = "LINKED_DOCS.json"
LINKED_DOCS_DIR = "linked-docs"
DEFAULT_HOSTS = ("wiki.corp.adobe.com",)
MAX_CHARS = 200_000
MAX_LINKED_FROM_PAGE = 10  # a page that is only an index of links: its linked wiki pages are read too
_URL = re.compile(r"https?://[^\s|\]\[<>\"'{}]+")
_PAGE_ID_PATH = re.compile(r"/pages/(\d+)(?:/|$)")
_DISPLAY_PATH = re.compile(r"^/display/([^/]+)/([^/?#]+)")
_BLOCK_TAGS = {"p", "div", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "table", "blockquote"}


_PULL_REQUEST = re.compile(r"https?://[^\s|\]\[<>\"'{}]+/pull/\d+")


def find_pull_requests(source: dict, own_name: str = "") -> list[str]:
    """Unique pull request URLs in the description and in comments not written by the automation."""
    texts = [source.get("description") or ""]
    texts += [c.get("body") or "" for c in source.get("comments") or [] if not own_name or c.get("author") != own_name]
    found: list[str] = []
    for text in texts:
        for url in _PULL_REQUEST.findall(text):
            if url not in found:
                found.append(url)
    return found


def find_links(source: dict, own_name: str = "", hosts: tuple[str, ...] = DEFAULT_HOSTS) -> list[str]:
    """Unique wiki page URLs in the description and in comments not written by the automation, in order."""
    texts = [source.get("description") or ""]
    texts += [c.get("body") or "" for c in source.get("comments") or [] if not own_name or c.get("author") != own_name]
    links: list[str] = []
    for text in texts:
        for url in _URL.findall(text):
            url = url.rstrip(".,;:)")
            if urllib.parse.urlsplit(url).hostname in hosts and url not in links:
                links.append(url)
    return links


class _TextParser(HTMLParser):
    """Confluence storage format to plain text: block elements become lines, table cells are joined by |."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag == "li":
            self.parts.append("\n- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def unknown_decl(self, data: str) -> None:
        # Code blocks (request examples, JSON schemas) are CDATA inside the code macro.
        if data.startswith("CDATA["):
            self.parts.append("\n" + data[len("CDATA["):] + "\n")


def storage_to_text(storage: str) -> str:
    parser = _TextParser()
    parser.feed(storage)
    lines = [" ".join(line.split()) for line in html.unescape("".join(parser.parts)).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class WikiClient:
    """Read-only Confluence Data Center REST client (Bearer personal access token)."""

    def __init__(self, base_url: str, token: str, verify_ssl: bool = True, timeout: float = 60.0) -> None:
        self.base_url, self.token, self.verify_ssl, self.timeout = base_url.rstrip("/"), token, verify_ssl, timeout

    @classmethod
    def from_env(cls) -> "WikiClient | None":
        token = os.getenv("WIKI_PAT") or ""
        if not token:
            return None
        verify = os.getenv("WIKI_SSL_VERIFY", "true").strip().lower() not in {"false", "0", "no"}
        return cls(os.getenv("WIKI_BASE_URL") or "https://wiki.corp.adobe.com", token, verify)

    def _get(self, path: str) -> Any:
        req = urllib.request.Request(self.base_url + path, method="GET")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/json")
        context = None
        if not self.verify_ssl:
            context = ssl.create_default_context()
            context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=context) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"wiki GET failed: HTTP {exc.code}") from None
        except ValueError:
            raise RuntimeError("wiki answered with a login page or non-JSON body; check WIKI_PAT") from None

    def page_id(self, url: str) -> str:
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parts.query)
        if query.get("pageId"):
            return query["pageId"][0]
        match = _PAGE_ID_PATH.search(parts.path)
        if match:
            return match.group(1)
        match = _DISPLAY_PATH.match(parts.path)
        if match:
            space, title = match.group(1), urllib.parse.unquote_plus(match.group(2))
            found = self._get("/rest/api/content?" + urllib.parse.urlencode({"spaceKey": space, "title": title}))
            results = found.get("results") or []
            if results:
                return str(results[0]["id"])
            raise RuntimeError(f"no page titled {title!r} in space {space}")
        raise RuntimeError("the link is not a wiki page link")

    def fetch(self, url: str) -> tuple[str, str, str]:
        """(page id, title, page text) of a wiki page link."""
        page_id = self.page_id(url)
        page = self._get(f"/rest/api/content/{page_id}?expand=body.storage,version")
        storage = ((page.get("body") or {}).get("storage") or {}).get("value") or ""
        return page_id, str(page.get("title") or ""), storage_to_text(storage)


def collect(source: dict, ticket_dir: Path, own_name: str = "", client: WikiClient | None = None,
            hosts: tuple[str, ...] = DEFAULT_HOSTS) -> list[dict]:
    """Fetch every linked wiki page into <ticket_dir>/linked-docs/ and write LINKED_DOCS.json. Never raises."""
    entries: list[dict] = []
    folder = ticket_dir / LINKED_DOCS_DIR
    queue = [(url, "") for url in find_links(source, own_name, hosts)]
    seen_urls, seen_pages = {url for url, _ in queue}, set()
    while queue:
        url, via = queue.pop(0)
        if client is None:
            entries.append({"url": url, "status": "UNREADABLE",
                            "reason": "WIKI_PAT is not set in the env file, so the runner cannot log in to the wiki"})
            continue
        try:
            page_id, title, text = client.fetch(url)
        except Exception as exc:  # noqa: BLE001 - one unreadable page must not stop the ticket
            entries.append({"url": url, "status": "UNREADABLE", "reason": str(exc)[:200], **({"via": via} if via else {})})
            continue
        if page_id in seen_pages:
            continue
        seen_pages.add(page_id)
        if not via:
            children = [u for u in find_links({"description": text}, "", hosts) if u not in seen_urls]
            for child in children[:MAX_LINKED_FROM_PAGE]:
                seen_urls.add(child)
                queue.append((child, url))
        if not text:
            entries.append({"url": url, "page_id": page_id, "title": title, "status": "UNREADABLE",
                            "reason": "the page has no text"})
            continue
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{page_id}.md"
        truncated = len(text) > MAX_CHARS
        path.write_text(f"# {title}\n\nSource: {url}\n\n{text[:MAX_CHARS]}\n", encoding="utf-8")
        entries.append({"url": url, "page_id": page_id, "title": title, "status": "READ",
                        "file": str(path.resolve()), "truncated": truncated, **({"via": via} if via else {})})
    for url in find_pull_requests(source, own_name):
        entries.append({"url": url, "kind": "pull_request", "status": "LINKED",
                        "note": "a proposed fix; read its diff in the matching clone"})
    (ticket_dir / LINKED_DOCS_FILE).write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    return entries


def unread(entries: list[dict]) -> list[str]:
    """One line per linked page the runner could not read."""
    return [f"linked page not read: {e['url']} ({e.get('reason') or 'unknown reason'})"
            for e in entries if e.get("status") == "UNREADABLE"]
