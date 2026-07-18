#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert DITA-OT issue exports into DITA topics for retrieval.

Input can be a JSON array, JSONL, a GitHub REST response, a GitHub GraphQL
``nodes`` response, or a mapping with ``issues``/``items``. The output is a
DITA map, one DITA topic per issue, and a manifest with stable checksums.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from lxml import etree


DEFAULT_OUTPUT_DIR = Path("dita-ot-issue-corpus")
DEFAULT_REPO = "dita-ot/dita-ot"
DITA_PROLOG = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
)
MAX_PARAGRAPH_CHARS = 1800


@dataclass(frozen=True)
class IssueRecord:
    number: int
    title: str
    state: str
    url: str
    body: str
    labels: list[str]
    comments: list[dict[str, str]]
    author: str
    created_at: str
    updated_at: str
    closed_at: str
    raw: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help="GitHub issue export JSON/JSONL path or GitHub issues URL, for example https://github.com/dita-ot/dita-ot/issues",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument(
        "--state",
        choices=("auto", "open", "closed", "all"),
        default="auto",
        help="GitHub issue state when --input is a URL; auto reads state:open/state:closed from the URL query",
    )
    parser.add_argument("--max-pages", type=int, default=0, help="GitHub API pages to fetch; 0 means all available pages")
    parser.add_argument("--per-page", type=int, default=100, help="GitHub API page size when --input is a URL")
    parser.add_argument("--include-comments-from-github", action="store_true", help="fetch comments for each GitHub issue URL result")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN", help="environment variable containing a GitHub token")
    parser.add_argument("--dataset-name", default="dita-ot-github-issues")
    parser.add_argument("--map-name", default="dita-ot-github-issues.ditamap")
    parser.add_argument("--limit", type=int, default=0, help="maximum issues to convert; 0 converts all")
    parser.add_argument("--reset", action="store_true", help="remove output directory before writing")
    parser.add_argument("--include-raw-json", action="store_true", help="store normalized issue JSON beside DITA topics")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    issues = load_issues(args.input, args)
    if args.limit > 0:
        issues = issues[: args.limit]
    if not issues:
        raise SystemExit(f"No issues found in {args.input}")

    if args.reset and args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    topics_dir = args.output_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    written_topics: list[dict[str, Any]] = []
    for issue in issues:
        topic_name = f"issue-{issue.number:05d}.dita"
        topic_path = topics_dir / topic_name
        topic_xml = issue_to_dita(issue, repo=args.repo)
        topic_path.write_text(topic_xml, encoding="utf-8", newline="\n")
        validate_topic(topic_path)
        if args.include_raw_json:
            (topics_dir / f"issue-{issue.number:05d}.json").write_text(
                json.dumps(issue.raw, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        written_topics.append(
            {
                "issue_number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "url": issue.url,
                "dita_file": f"topics/{topic_name}",
                "labels": issue.labels,
                "content_hash": "sha256:" + hashlib.sha256(topic_xml.encode("utf-8")).hexdigest(),
            }
        )

    map_path = args.output_dir / args.map_name
    map_path.write_text(build_map(args.dataset_name, written_topics), encoding="utf-8", newline="\n")
    validate_map(map_path, expected_topicrefs=len(written_topics))

    manifest = build_manifest(args, written_topics)
    manifest_path = args.output_dir / "dataset-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print(
        json.dumps(
            {
                "dataset_name": args.dataset_name,
                "repo": args.repo,
                "issues_converted": len(written_topics),
                "output_dir": str(args.output_dir.resolve()),
                "map": str(map_path.resolve()),
                "manifest": str(manifest_path.resolve()),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def load_issues(input_value: str, args: argparse.Namespace) -> list[IssueRecord]:
    if looks_like_url(input_value):
        raw_items = fetch_github_issues(
            input_value,
            state=args.state,
            max_pages=args.max_pages,
            per_page=args.per_page,
            include_comments=args.include_comments_from_github,
            token=resolve_github_token(args.github_token_env),
        )
        return [normalize_issue(item) for item in raw_items if not is_pull_request(item)]

    path = Path(input_value)
    if not path.exists():
        raise FileNotFoundError(
            f"Input not found: {input_value}. Pass a real JSON/JSONL file path or a GitHub issues URL."
        )
    text = path.read_text(encoding="utf-8-sig")
    data: Any
    if path.suffix.lower() == ".jsonl":
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = json.loads(text)
    raw_items = extract_issue_items(data)
    return [normalize_issue(item) for item in raw_items if not is_pull_request(item)]


def looks_like_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def resolve_github_token(env_name: str) -> str:
    token = os.environ.get(env_name, "")
    if token or os.name != "nt":
        return token
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, env_name)
            return str(value or "")
    except OSError:
        return ""


def fetch_github_issues(
    issues_url: str,
    *,
    state: str,
    max_pages: int,
    per_page: int,
    include_comments: bool,
    token: str,
) -> list[dict[str, Any]]:
    owner, repo = parse_github_issues_url(issues_url)
    state = resolve_github_issue_state(issues_url, state)
    if token:
        return fetch_github_issues_graphql(
            owner,
            repo,
            state=state,
            max_pages=max_pages,
            per_page=per_page,
            include_comments=include_comments,
            token=token,
        )
    if max_pages == 0:
        max_pages = 10
        print(
            "WARN: GITHUB_TOKEN is not available in this PowerShell session. "
            "Using REST fallback for first 10 pages only. "
            "Set $env:GITHUB_TOKEN in this session or open a new PowerShell after setx for full cursor pagination."
        )
    per_page = min(max(per_page, 1), 100)
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        if max_pages and page > max_pages:
            break
        api_url = (
            f"https://api.github.com/repos/{owner}/{repo}/issues"
            f"?state={urllib.parse.quote(state)}&per_page={per_page}&page={page}"
        )
        batch = github_get_json(api_url, token=token)
        if not isinstance(batch, list):
            raise ValueError(f"GitHub API returned unexpected response for {api_url}")
        if not batch:
            break
        for item in batch:
            if include_comments and isinstance(item, dict) and item.get("comments_url") and item.get("comments"):
                comments = github_get_json(str(item["comments_url"]), token=token)
                if isinstance(comments, list):
                    item["comments"] = comments
            items.append(item)
        if len(batch) < per_page:
            break
        page += 1
    return items


def fetch_github_issues_graphql(
    owner: str,
    repo: str,
    *,
    state: str,
    max_pages: int,
    per_page: int,
    include_comments: bool,
    token: str,
) -> list[dict[str, Any]]:
    per_page = min(max(per_page, 1), 100)
    after: str | None = None
    page = 1
    items: list[dict[str, Any]] = []
    state_filter = ""
    if state in {"open", "closed"}:
        state_filter = f", states: [{state.upper()}]"
    comment_count = 50 if include_comments else 0
    query = f"""
query($owner: String!, $repo: String!, $first: Int!, $after: String) {{
  repository(owner: $owner, name: $repo) {{
    issues(first: $first, after: $after, orderBy: {{field: CREATED_AT, direction: DESC}}{state_filter}) {{
      pageInfo {{
        hasNextPage
        endCursor
      }}
      nodes {{
        number
        title
        state
        url
        body
        createdAt
        updatedAt
        closedAt
        author {{
          login
        }}
        labels(first: 50) {{
          nodes {{
            name
          }}
        }}
        comments(first: {comment_count}) {{
          nodes {{
            body
            createdAt
            author {{
              login
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""
    while True:
        if max_pages and page > max_pages:
            break
        payload = {"query": query, "variables": {"owner": owner, "repo": repo, "first": per_page, "after": after}}
        response = github_post_json("https://api.github.com/graphql", payload, token=token)
        if response.get("errors"):
            raise RuntimeError(f"GitHub GraphQL failed: {json.dumps(response['errors'], ensure_ascii=False)}")
        issues = response.get("data", {}).get("repository", {}).get("issues", {})
        nodes = issues.get("nodes") or []
        items.extend(node for node in nodes if isinstance(node, dict))
        page_info = issues.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")
        page += 1
    return items


def parse_github_issues_url(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() != "github.com":
        raise ValueError(f"Only github.com issue URLs are supported, got: {url}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[2] != "issues":
        raise ValueError(f"Expected GitHub issues URL like https://github.com/owner/repo/issues, got: {url}")
    return parts[0], parts[1]


def resolve_github_issue_state(url: str, state: str) -> str:
    if state != "auto":
        return state
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query).get("q", [])
    query_text = " ".join(query).lower()
    if "state:closed" in query_text or "is:closed" in query_text:
        return "closed"
    if "state:open" in query_text or "is:open" in query_text:
        return "open"
    return "all"


def github_get_json(url: str, *, token: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "aem-guides-dataset-studio-dita-ot-issue-converter/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in {403, 429}:
            rate_remaining = exc.headers.get("X-RateLimit-Remaining", "")
            rate_reset = exc.headers.get("X-RateLimit-Reset", "")
            auth_hint = (
                "A GitHub token was provided, but access/rate-limit still failed."
                if token
                else "No GitHub token was provided. Set GITHUB_TOKEN to a GitHub personal access token, then rerun."
            )
            raise RuntimeError(
                "GitHub API rate-limit/access failure "
                f"HTTP {exc.code} for {url}. {auth_hint} "
                f"X-RateLimit-Remaining={rate_remaining or 'unknown'} "
                f"X-RateLimit-Reset={rate_reset or 'unknown'}. "
                "For PowerShell: $env:GITHUB_TOKEN='YOUR_TOKEN_HERE'. "
                "You can also export issues with GitHub CLI and pass the JSON file as --input."
            ) from exc
        raise RuntimeError(f"GitHub API failed HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API request failed for {url}: {exc}") from exc


def github_post_json(url: str, payload: dict[str, Any], *, token: str) -> Any:
    if not token:
        raise RuntimeError("GitHub GraphQL requires GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "aem-guides-dataset-studio-dita-ot-issue-converter/1.0",
        "Authorization": f"Bearer {token}",
    }
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL failed HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub GraphQL request failed for {url}: {exc}") from exc


def extract_issue_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("issues", "items", "nodes"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    repository = data.get("repository")
    if isinstance(repository, dict):
        issues = repository.get("issues")
        if isinstance(issues, dict) and isinstance(issues.get("nodes"), list):
            return [item for item in issues["nodes"] if isinstance(item, dict)]
    search = data.get("search")
    if isinstance(search, dict) and isinstance(search.get("nodes"), list):
        return [item for item in search["nodes"] if isinstance(item, dict)]
    return [data]


def normalize_issue(raw: dict[str, Any]) -> IssueRecord:
    labels = normalize_labels(raw.get("labels"))
    comments = normalize_comments(raw.get("comments"))
    number = int(raw.get("number") or raw.get("id") or 0)
    if number <= 0:
        raise ValueError(f"issue has no usable number/id: {raw!r}")
    return IssueRecord(
        number=number,
        title=str(raw.get("title") or f"Issue {number}").strip(),
        state=str(raw.get("state") or "").lower(),
        url=str(raw.get("html_url") or raw.get("url") or raw.get("resourcePath") or "").strip(),
        body=str(raw.get("body") or raw.get("bodyText") or "").strip(),
        labels=labels,
        comments=comments,
        author=normalize_author(raw.get("user") or raw.get("author")),
        created_at=str(raw.get("created_at") or raw.get("createdAt") or ""),
        updated_at=str(raw.get("updated_at") or raw.get("updatedAt") or ""),
        closed_at=str(raw.get("closed_at") or raw.get("closedAt") or ""),
        raw=raw,
    )


def normalize_labels(value: Any) -> list[str]:
    if isinstance(value, dict) and isinstance(value.get("nodes"), list):
        value = value["nodes"]
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        if isinstance(item, str):
            labels.append(item)
        elif isinstance(item, dict):
            label = item.get("name") or item.get("title")
            if label:
                labels.append(str(label))
    return sorted(set(labels), key=str.lower)


def normalize_comments(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict) and isinstance(value.get("nodes"), list):
        value = value["nodes"]
    if not isinstance(value, list):
        return []
    comments: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or item.get("bodyText") or "").strip()
        if not body:
            continue
        comments.append(
            {
                "author": normalize_author(item.get("user") or item.get("author")),
                "created_at": str(item.get("created_at") or item.get("createdAt") or ""),
                "body": body,
            }
        )
    return comments


def normalize_author(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("login") or value.get("name") or "")
    return ""


def is_pull_request(raw: dict[str, Any]) -> bool:
    return bool(raw.get("pull_request")) or str(raw.get("__typename") or "").lower() == "pullrequest"


def issue_to_dita(issue: IssueRecord, *, repo: str) -> str:
    topic_id = f"dita_ot_issue_{issue.number:05d}"
    title = f"DITA-OT Issue #{issue.number}: {issue.title}"
    labels_text = ", ".join(issue.labels) if issue.labels else "none"
    body_sections = markdownish_to_blocks(issue.body)
    comment_sections = [
        (f"Comment {index:03d}", f"Author: {comment['author'] or 'unknown'}\nCreated: {comment['created_at']}\n\n{comment['body']}")
        for index, comment in enumerate(issue.comments, start=1)
    ]
    source_url = issue.url or f"https://github.com/{repo}/issues/{issue.number}"
    content_hash = hashlib.sha256(json.dumps(issue.raw, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    lines = [
        DITA_PROLOG.rstrip(),
        f'<topic id="{topic_id}" xml:lang="en-US">',
        f"  <title>{xml_text(title)}</title>",
        f"  <shortdesc>GitHub issue evidence from {xml_text(repo)} for DITA-OT behavior, defects, regressions, and edge cases.</shortdesc>",
        "  <prolog>",
        "    <metadata>",
        othermeta("source-type", "github-issue"),
        othermeta("source-system", "github"),
        othermeta("source-repo", repo),
        othermeta("source-url", source_url),
        othermeta("issue-number", str(issue.number)),
        othermeta("issue-state", issue.state),
        othermeta("issue-labels", labels_text),
        othermeta("issue-author", issue.author),
        othermeta("created-at", issue.created_at),
        othermeta("updated-at", issue.updated_at),
        othermeta("closed-at", issue.closed_at),
        othermeta("content-hash", f"sha256:{content_hash}"),
        othermeta("converted-at", datetime.now(timezone.utc).isoformat()),
        "    </metadata>",
        "  </prolog>",
        "  <body>",
        '    <section id="issue_facts">',
        "      <title>Issue facts</title>",
        f"      <p>Repository: {xml_text(repo)}</p>",
        f"      <p>Issue number: {issue.number}</p>",
        f"      <p>State: {xml_text(issue.state or 'unknown')}</p>",
        f"      <p>Labels: {xml_text(labels_text)}</p>",
        f'      <p>Source: <xref href="{xml_attr(source_url)}" scope="external" format="html">{xml_text(source_url)}</xref></p>',
        "    </section>",
        '    <section id="retrieval_summary">',
        "      <title>Retrieval summary</title>",
        f"      <p>{xml_text(build_retrieval_summary(issue))}</p>",
        "    </section>",
        '    <section id="issue_body">',
        "      <title>Issue body</title>",
    ]
    lines.extend(render_text_blocks(body_sections or [("Paragraph", issue.body or "No issue body was provided.")], indent="      "))
    lines.append("    </section>")
    if comment_sections:
        lines.extend(['    <section id="issue_comments">', "      <title>Issue comments</title>"])
        lines.extend(render_text_blocks(comment_sections, indent="      "))
        lines.append("    </section>")
    lines.extend(["  </body>", "</topic>"])
    return "\n".join(lines) + "\n"


def build_retrieval_summary(issue: IssueRecord) -> str:
    signal_terms = []
    text = f"{issue.title}\n{issue.body}".lower()
    for needle in (
        "error",
        "exception",
        "crash",
        "regression",
        "conref",
        "keyref",
        "xref",
        "map",
        "pdf",
        "html",
        "dita-ot",
        "plugin",
        "validation",
        "transform",
        "publishing",
    ):
        if needle in text:
            signal_terms.append(needle)
    labels = ", ".join(issue.labels) if issue.labels else "none"
    signals = ", ".join(signal_terms) if signal_terms else "general issue behavior"
    return f"Issue #{issue.number} is {issue.state or 'unknown'} with labels {labels}. Retrieval signals: {signals}."


def markdownish_to_blocks(text: str) -> list[tuple[str, str]]:
    text = repair_text(text)
    if not text.strip():
        return []
    blocks: list[tuple[str, str]] = []
    current_title = "Description"
    current_parts: list[str] = []
    in_code = False
    code_parts: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if in_code:
                blocks.append(("Code example", "\n".join(code_parts).strip()))
                code_parts = []
                in_code = False
            else:
                flush_block(blocks, current_title, current_parts)
                current_parts = []
                in_code = True
            continue
        if in_code:
            code_parts.append(line)
            continue
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            flush_block(blocks, current_title, current_parts)
            current_title = heading.group(1).strip()
            current_parts = []
            continue
        current_parts.append(line)
    if in_code and code_parts:
        blocks.append(("Code example", "\n".join(code_parts).strip()))
    flush_block(blocks, current_title, current_parts)
    return blocks


def flush_block(blocks: list[tuple[str, str]], title: str, parts: list[str]) -> None:
    text = "\n".join(parts).strip()
    if text:
        blocks.append((title or "Description", text))


def render_text_blocks(blocks: list[tuple[str, str]], *, indent: str) -> list[str]:
    lines: list[str] = []
    for index, (title, text) in enumerate(blocks, start=1):
        lines.append(f'{indent}<p outputclass="issue-block-title">{xml_text(title)}</p>')
        if "\n" in text and (title.lower().startswith("code") or looks_like_code(text)):
            lines.append(f'{indent}<codeblock xml:space="preserve">{xml_text(text)}</codeblock>')
        else:
            for paragraph in split_paragraphs(text):
                lines.append(f"{indent}<p>{xml_text(paragraph)}</p>")
    return lines


def split_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    for part in re.split(r"\n\s*\n", text.strip()):
        part = re.sub(r"\s*\n\s*", " ", part).strip()
        if not part:
            continue
        while len(part) > MAX_PARAGRAPH_CHARS:
            paragraphs.append(part[:MAX_PARAGRAPH_CHARS].rstrip())
            part = part[MAX_PARAGRAPH_CHARS:].lstrip()
        paragraphs.append(part)
    return paragraphs


def looks_like_code(text: str) -> bool:
    code_markers = ("<", "/>", "{", "}", "Exception", "Traceback", "at ", "org.dita")
    return any(marker in text for marker in code_markers)


def build_map(dataset_name: str, topics: list[dict[str, Any]]) -> str:
    map_id = safe_id(dataset_name)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">',
        f'<map id="{map_id}" xml:lang="en-US">',
        f"  <title>{xml_text(dataset_name)}</title>",
    ]
    for topic in sorted(topics, key=lambda row: int(row["issue_number"])):
        navtitle = f"DITA-OT Issue #{topic['issue_number']}: {topic['title']}"
        lines.append(f'  <topicref href="{xml_attr(topic["dita_file"])}" type="topic" navtitle="{xml_attr(navtitle)}"/>')
    lines.append("</map>")
    return "\n".join(lines) + "\n"


def build_manifest(args: argparse.Namespace, topics: list[dict[str, Any]]) -> dict[str, Any]:
    states: dict[str, int] = {}
    labels: dict[str, int] = {}
    for topic in topics:
        states[str(topic["state"] or "unknown")] = states.get(str(topic["state"] or "unknown"), 0) + 1
        for label in topic["labels"]:
            labels[label] = labels.get(label, 0) + 1
    return {
        "dataset_name": args.dataset_name,
        "source_repo": args.repo,
        "source_input": str(args.input),
        "entry_map": args.map_name,
        "issue_count": len(topics),
        "topic_count": len(topics),
        "state_counts": dict(sorted(states.items())),
        "label_counts": dict(sorted(labels.items())),
        "topics": topics,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "converter_version": "dita-ot-issue-to-dita/1.0",
    }


def validate_topic(path: Path) -> None:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<!DOCTYPE[^>]+>\s*", "", text)
    root = etree.fromstring(text.encode("utf-8"), parser)
    if root.tag != "topic":
        raise ValueError(f"{path} root is not <topic>")
    if not root.get("id"):
        raise ValueError(f"{path} missing topic id")


def validate_map(path: Path, *, expected_topicrefs: int) -> None:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<!DOCTYPE[^>]+>\s*", "", text)
    root = etree.fromstring(text.encode("utf-8"), parser)
    if root.tag != "map":
        raise ValueError(f"{path} root is not <map>")
    topicrefs = root.xpath(".//*[local-name()='topicref']")
    if len(topicrefs) != expected_topicrefs:
        raise ValueError(f"{path} expected {expected_topicrefs} topicrefs, found {len(topicrefs)}")


def othermeta(name: str, content: str) -> str:
    return f'      <othermeta name="{xml_attr(name)}" content="{xml_attr(content)}"/>'


def repair_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return strip_invalid_xml_chars(text)


def strip_invalid_xml_chars(text: str) -> str:
    return "".join(char for char in text if is_valid_xml_char(char))


def is_valid_xml_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        codepoint == 0x09
        or codepoint == 0x0A
        or codepoint == 0x0D
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def safe_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    value = value.strip("._-")
    if not value or not re.match(r"^[A-Za-z_]", value):
        value = f"dataset_{value}"
    return value


def xml_text(value: Any) -> str:
    return escape(strip_invalid_xml_chars(str(value or "")))


def xml_attr(value: Any) -> str:
    return escape(strip_invalid_xml_chars(str(value or "")), {'"': "&quot;", "'": "&apos;"})


if __name__ == "__main__":
    raise SystemExit(main())
