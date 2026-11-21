"""Fetch the Figma designs a Jira ticket links to, so the UAC can be checked against the intended UI.

The nightly Copilot session runs unattended, so it cannot complete the browser login the Figma MCP server
needs. The runner therefore reads every linked design itself through the Figma REST API with a personal
access token (FIGMA_TOKEN in the env file, scope file_content:read). Access is read-only: the runner only
sends GET requests, and the token is sent to the Figma API alone, never to the image download host.

For every linked frame it writes, into <ticket>/figma-designs/:
  - <file>_<node>.md   an outline of the frame: layer types and names, every text string, component
                       variant names and instance property values, hidden layers marked and not expanded;
  - <file>_<node>.png  the frame rendered by Figma (PNG, scale 1).
and lists every link in FIGMA_DESIGNS.json:

    [{"url": "...", "file_key": "AbC123", "node_id": "12:34", "status": "READ", "title": "File / Frame",
      "outline": "/abs/path.md", "image": "/abs/path.png", "last_modified": "...", "version": "..."},
     {"url": "...", "status": "UNREADABLE", "reason": "FIGMA_TOKEN is not set ..."}]

Links are taken from the description and from comments not written by the automation. A link without a
node-id reads the file's first page and renders up to MAX_FRAMES_PER_FILE of its top-level frames.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from linked_docs import find_links

FIGMA_DESIGNS_FILE = "FIGMA_DESIGNS.json"
FIGMA_DESIGNS_DIR = "figma-designs"
DEFAULT_HOSTS = ("figma.com", "www.figma.com")
DEFAULT_API_BASE = "https://api.figma.com"
MAX_DESIGNS = 5               # links read per ticket; the rest are listed as SKIPPED
MAX_FRAMES_PER_FILE = 3       # frames rendered when a link names no node
MAX_OUTLINE_LINES = 1500
MAX_TEXT_CHARS = 400          # one text layer in the outline
MAX_IMAGE_BYTES = 15 * 1024 * 1024
_FILE_KINDS = {"design", "file", "proto", "board"}
_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


def parse_link(url: str) -> tuple[str, str]:
    """(file key, node id or "") of a Figma link; ("", "") when the link names no design file.

    https://www.figma.com/design/<key>/<name>?node-id=12-34  -> ("<key>", "12:34")
    https://www.figma.com/design/<key>/branch/<branch>/<name> -> ("<branch>", "")
    """
    parts = urllib.parse.urlsplit(url)
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) < 2 or segments[0] not in _FILE_KINDS:
        return "", ""
    key = segments[1]
    if len(segments) >= 4 and segments[2] == "branch":
        key = segments[3]
    node = (urllib.parse.parse_qs(parts.query).get("node-id") or [""])[0]
    # The URL form uses "-" where the API uses ":" (12-34 -> 12:34, I1-2;3-4 -> I1:2;3:4).
    return key, node.replace("-", ":")


def _line(node: dict, depth: int) -> str:
    kind, name = str(node.get("type") or "NODE"), str(node.get("name") or "")
    line = f"{'  ' * depth}- {kind} \"{name}\""
    if kind == "TEXT" and node.get("characters"):
        text = " ".join(str(node["characters"]).split())
        line += f": {text[:MAX_TEXT_CHARS]}" + (" [...]" if len(text) > MAX_TEXT_CHARS else "")
    props = node.get("componentProperties") or {}
    if isinstance(props, dict) and props:
        values = ", ".join(f"{k.split('#')[0]}={(v or {}).get('value')}" for k, v in props.items())
        line += f" {{{values}}}"
    if node.get("visible") is False:
        line += " (hidden)"
    return line


def outline(node: dict) -> tuple[str, bool]:
    """Indented text outline of a node tree; (text, truncated). Hidden layers are listed, not expanded."""
    lines: list[str] = []
    stack: list[tuple[dict, int]] = [(node, 0)]
    while stack:
        current, depth = stack.pop()
        if len(lines) >= MAX_OUTLINE_LINES:
            return "\n".join(lines), True
        lines.append(_line(current, depth))
        if current.get("visible") is False:
            continue
        children = [c for c in current.get("children") or [] if isinstance(c, dict)]
        stack.extend((child, depth + 1) for child in reversed(children))
    return "\n".join(lines), False


class FigmaClient:
    """Read-only Figma REST client (personal access token in the X-Figma-Token header)."""

    def __init__(self, token: str, base_url: str = DEFAULT_API_BASE, timeout: float = 60.0,
                 opener: Callable[..., Any] | None = None) -> None:
        self.token, self.base_url, self.timeout = token, base_url.rstrip("/"), timeout
        self._open = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> "FigmaClient | None":
        token = (os.getenv("FIGMA_TOKEN") or "").strip()
        if not token:
            return None
        return cls(token, os.getenv("FIGMA_API_BASE_URL") or DEFAULT_API_BASE)

    def _get(self, path: str) -> Any:
        req = urllib.request.Request(self.base_url + path, method="GET")
        req.add_header("X-Figma-Token", self.token)
        req.add_header("Accept", "application/json")
        try:
            with self._open(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            hint = {403: "the token cannot open this file: share it with the token's account or check the "
                         "file_content:read scope",
                    404: "the file or node does not exist or is not shared with the token's account",
                    429: "Figma rate limit reached; the next run retries"}.get(exc.code, "")
            raise RuntimeError(f"Figma GET failed: HTTP {exc.code}" + (f" ({hint})" if hint else "")) from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Figma API not reachable: {exc.reason}") from None
        except ValueError:
            raise RuntimeError("Figma answered with a non-JSON body") from None

    def nodes(self, file_key: str, node_ids: list[str]) -> dict:
        query = urllib.parse.urlencode({"ids": ",".join(node_ids)})
        return self._get(f"/v1/files/{urllib.parse.quote(file_key)}/nodes?{query}")

    def first_page_frames(self, file_key: str) -> tuple[dict, list[str]]:
        """(file metadata, ids of the first page's top-level frames)."""
        data = self._get(f"/v1/files/{urllib.parse.quote(file_key)}?depth=2")
        pages = ((data.get("document") or {}).get("children")) or []
        frames = [c for c in (pages[0].get("children") or []) if c.get("visible") is not False] if pages else []
        return data, [str(f["id"]) for f in frames if f.get("id")][:MAX_FRAMES_PER_FILE]

    def render(self, file_key: str, node_ids: list[str]) -> dict:
        """{node id: temporary image URL or None} for PNG renders at scale 1."""
        query = urllib.parse.urlencode({"ids": ",".join(node_ids), "format": "png", "scale": "1"})
        data = self._get(f"/v1/images/{urllib.parse.quote(file_key)}?{query}")
        if data.get("err"):
            raise RuntimeError(f"Figma could not render the frame: {data['err']}")
        return data.get("images") or {}

    def download(self, url: str) -> bytes:
        """The rendered image. The Figma token is not sent: the URL is a signed link on another host."""
        if urllib.parse.urlsplit(url).scheme != "https":
            raise RuntimeError("Figma returned a non-https image link")
        with self._open(urllib.request.Request(url, method="GET"), timeout=self.timeout) as resp:
            body = resp.read(MAX_IMAGE_BYTES + 1)
        if len(body) > MAX_IMAGE_BYTES:
            raise RuntimeError("the rendered image is larger than 15 MB")
        return body


def _read_link(client: FigmaClient, url: str, file_key: str, node_id: str, folder: Path) -> list[dict]:
    """One entry per frame the link names (one, or up to MAX_FRAMES_PER_FILE without a node-id)."""
    if node_id:
        data = client.nodes(file_key, [node_id])
        documents = {node_id: ((data.get("nodes") or {}).get(node_id) or {}).get("document")}
    else:
        data, ids = client.first_page_frames(file_key)
        if not ids:
            raise RuntimeError("the file's first page has no visible frame; link a frame with node-id")
        frames = client.nodes(file_key, ids)
        documents = {i: ((frames.get("nodes") or {}).get(i) or {}).get("document") for i in ids}
    missing = [i for i, doc in documents.items() if not doc]
    if missing and len(missing) == len(documents):
        raise RuntimeError(f"node {', '.join(missing)} not found in the file")
    try:
        images = client.render(file_key, [i for i, doc in documents.items() if doc])
        render_error = ""
    except Exception as exc:  # noqa: BLE001 - the outline is still evidence without the picture
        images, render_error = {}, str(exc)[:200]
    file_name = str(data.get("name") or file_key)
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for node, document in documents.items():
        base = {"url": url, "file_key": file_key, "node_id": node}
        if not document:
            entries.append({**base, "status": "UNREADABLE", "reason": "node not found in the file"})
            continue
        stem = f"{_SAFE.sub('_', file_key)}_{_SAFE.sub('_', node)}"
        title = f"{file_name} / {document.get('name') or node}"
        text, truncated = outline(document)
        outline_path = folder / f"{stem}.md"
        outline_path.write_text(f"# {title}\n\nSource: {url}\nFigma node: {node}\n"
                                f"Last modified: {data.get('lastModified') or ''}\n\n{text}\n", encoding="utf-8")
        entry = {**base, "status": "READ", "title": title, "outline": str(outline_path.resolve()),
                 "truncated": truncated, "last_modified": str(data.get("lastModified") or ""),
                 "version": str(data.get("version") or "")}
        image_url = images.get(node)
        try:
            if not image_url:
                raise RuntimeError(render_error or "Figma returned no image for the frame")
            image_path = folder / f"{stem}.png"
            image_path.write_bytes(client.download(image_url))
            entry["image"] = str(image_path.resolve())
        except Exception as exc:  # noqa: BLE001 - an outline without the picture is still READ
            entry["image_error"] = str(exc)[:200]
        entries.append(entry)
    return entries


def collect(source: dict, ticket_dir: Path, own_name: str = "", client: FigmaClient | None = None,
            hosts: tuple[str, ...] = DEFAULT_HOSTS, max_designs: int = MAX_DESIGNS) -> list[dict]:
    """Fetch every linked Figma design into <ticket_dir>/figma-designs/ and write FIGMA_DESIGNS.json.

    Never raises. Writes the JSON list (empty when the ticket links no design)."""
    entries: list[dict] = []
    folder = ticket_dir / FIGMA_DESIGNS_DIR
    seen: set[tuple[str, str]] = set()
    read = 0
    for url in find_links(source, own_name, hosts):
        file_key, node_id = parse_link(url)
        if not file_key or (file_key, node_id) in seen:
            continue
        seen.add((file_key, node_id))
        if client is None:
            entries.append({"url": url, "file_key": file_key, "node_id": node_id, "status": "UNREADABLE",
                            "reason": "FIGMA_TOKEN is not set in the env file, so the runner cannot read Figma"})
            continue
        if read >= max_designs:
            entries.append({"url": url, "file_key": file_key, "node_id": node_id, "status": "SKIPPED",
                            "reason": f"more than {max_designs} Figma links on the ticket"})
            continue
        read += 1
        try:
            entries.extend(_read_link(client, url, file_key, node_id, folder))
        except Exception as exc:  # noqa: BLE001 - one unreadable design must not stop the ticket
            entries.append({"url": url, "file_key": file_key, "node_id": node_id, "status": "UNREADABLE",
                            "reason": str(exc)[:200]})
    (ticket_dir / FIGMA_DESIGNS_FILE).write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    return entries


def unread(entries: list[dict]) -> list[str]:
    """One line per linked Figma design the runner could not read."""
    return [f"Figma design not read: {e['url']} ({e.get('reason') or 'unknown reason'})"
            for e in entries if e.get("status") == "UNREADABLE"]
