"""
Resolve Jira issue key / browse URL into full issue text for generate-from-text (chat ZIP flow).

Only uses configured JIRA_BASE_URL + auth — never fetches arbitrary user URLs (SSRF-safe).
"""
from __future__ import annotations

import os
import re
from typing import Optional, Tuple

from app.core.structured_logging import get_structured_logger
from app.services.jira_client import JiraClient, extract_description_from_issue

logger = get_structured_logger(__name__)

# Whole-message issue key (Jira style: PROJECT-123)
_SINGLE_ISSUE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
# /browse/PROJ-123 in URL path
_BROWSE_PATH = re.compile(r"/browse/([A-Za-z][A-Za-z0-9_]*-\d+)", re.IGNORECASE)
# Query params sometimes used by Jira UIs
_QUERY_KEY = re.compile(
    r"(?:^|[?&])(?:selectedIssue|issueKey|issue_key)=([A-Za-z][A-Za-z0-9_]*-\d+)",
    re.IGNORECASE,
)
_EMBEDDED_ISSUE_KEY = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*-\d+)\b")
_EMBEDDED_GENERATION_VERB = re.compile(
    r"\b(generate|create|build|make|draft|prepare|produce|write|convert|turn)\b",
    re.IGNORECASE,
)
_EMBEDDED_GENERATION_OBJECT = re.compile(
    r"\b(data|dita|xml|topic|topics|map|ditamap|bundle|zip|content|docs?|documentation)\b",
    re.IGNORECASE,
)
_EMBEDDED_NON_GENERATION_PATTERN = re.compile(
    r"^\s*(what|how|why|where|when|who|is|are|can|could|would|should|do|does)\b|"
    r"^\s*(find|search|show|lookup|look\s+up|status|comment|discussion|related|similar|history|"
    r"explain|define|compare)\b",
    re.IGNORECASE,
)

# Do not scan megabyte pastes for keys
_MAX_SHORTCUT_LEN = 2048
_MAX_URL_ONLY_LEN = 800
_MAX_EMBEDDED_GENERATION_LEN = 400


def _normalize_issue_key(key: str) -> str:
    return (key or "").strip().upper()


def _issue_key_safe_for_api(key: str) -> bool:
    """Strict key shape for Jira REST path segment (no injection)."""
    return bool(key and re.match(r"^[A-Z][A-Z0-9_]*-\d+$", key))


def is_jira_shortcut_input(text: str) -> bool:
    """
    True if the user message is only an issue key or a short URL line we should try to resolve.
    Long pastes are never treated as shortcuts (avoid false positives).
    """
    t = (text or "").strip()
    if not t or len(t) > _MAX_SHORTCUT_LEN:
        return False
    if _SINGLE_ISSUE_KEY.match(t):
        return True
    if t.startswith("http") and len(t) <= _MAX_URL_ONLY_LEN:
        if _BROWSE_PATH.search(t) or _QUERY_KEY.search(t):
            return True
    return False


def extract_issue_key_from_shortcut(text: str) -> Optional[str]:
    """Extract issue key from shortcut input; None if ambiguous or missing."""
    t = (text or "").strip()
    if not t or len(t) > _MAX_SHORTCUT_LEN:
        return None
    m = _SINGLE_ISSUE_KEY.match(t)
    if m:
        return _normalize_issue_key(m.group(0))
    if t.startswith("http"):
        m2 = _BROWSE_PATH.search(t)
        if m2:
            return _normalize_issue_key(m2.group(1))
        m3 = _QUERY_KEY.search(t)
        if m3:
            return _normalize_issue_key(m3.group(1))
    return None


def extract_issue_key_from_generation_request(text: str) -> Optional[str]:
    """Extract a Jira issue key from a short generation-style request.

    Supports plain Jira shortcuts such as ``GUIDES-123`` and short imperative
    requests like ``Create data for GUIDES-123`` without treating search or
    question phrasing as generation.
    """
    t = (text or "").strip()
    if not t or len(t) > _MAX_EMBEDDED_GENERATION_LEN:
        return None

    shortcut = extract_issue_key_from_shortcut(t)
    if shortcut:
        return shortcut

    matches = [m.group(1) for m in _EMBEDDED_ISSUE_KEY.finditer(t)]
    if len(matches) != 1:
        return None
    if "?" in t:
        return None
    if not _EMBEDDED_GENERATION_VERB.search(t):
        return None
    if _EMBEDDED_NON_GENERATION_PATTERN.search(t):
        return None
    if not (
        _EMBEDDED_GENERATION_OBJECT.search(t)
        or re.search(rf"\b(?:for|from)\s+{re.escape(matches[0])}\b", t, re.IGNORECASE)
    ):
        return None
    return _normalize_issue_key(matches[0])


def _jira_client_ready(client: JiraClient) -> bool:
    if not (client.base_url or "").strip():
        return False
    return bool(
        (client.username and client.password)
        or (client.email and client.api_token)
    )


def _extract_section(text: str, heading_pattern: str, max_chars: int = 3000) -> str:
    """Extract a section from description text following a heading pattern.

    Returns the text between the matched heading and the next heading (or end).
    """
    m = re.search(heading_pattern, text, re.IGNORECASE)
    if not m:
        return ""
    start = m.end()
    # Find the next heading-like line (## or h3. or ALLCAPS followed by colon/newline)
    next_heading = re.search(
        r"\n(?:##\s|h[1-6]\.\s|(?:Steps?\s+to|Expected|Actual|Acceptance|Environment|Comments?)\s)",
        text[start:],
        re.IGNORECASE,
    )
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()[:max_chars]


_TEXT_ATTACHMENT_EXTENSIONS = frozenset(
    ".txt .log .xml .dita .ditamap .json .yaml .yml .md .csv .html .htm .xhtml .snippet .sample .cfg .properties".split()
)
_IMAGE_ATTACHMENT_EXTENSIONS = frozenset(".png .jpg .jpeg .gif .webp .svg .bmp .tiff .tif".split())
_MAX_ATTACHMENT_BYTES = int(os.getenv("JIRA_MAX_ATTACHMENT_BYTES", "80000"))
_MAX_ATTACHMENTS = int(os.getenv("JIRA_MAX_ATTACHMENTS", "5"))
_MAX_COMMENTS = int(os.getenv("JIRA_MAX_COMMENTS", "30"))  # was hardcoded 20


def _read_attachment_text(client: JiraClient, att: dict) -> str:
    """Download a Jira attachment and return its text content (empty if binary/too large)."""
    content_url = att.get("content") or att.get("url") or ""
    filename = (att.get("filename") or "").lower()
    mime = (att.get("mimeType") or att.get("mime_type") or "").lower()
    size = int(att.get("size") or 0)

    # Only read text-readable files; skip huge files
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    is_text = (
        ext in _TEXT_ATTACHMENT_EXTENSIONS
        or mime.startswith("text/")
        or mime in ("application/json", "application/xml", "application/yaml", "application/x-yaml")
    )
    if not is_text:
        return ""
    if size > _MAX_ATTACHMENT_BYTES * 2:
        # Warn so operators know context was truncated — set JIRA_MAX_ATTACHMENT_BYTES to include it
        logger.warning_structured(
            "jira_attachment_skipped_too_large",
            extra_fields={"filename": att.get("filename"), "size_kb": size // 1024, "limit_kb": _MAX_ATTACHMENT_BYTES // 1024},
        )
        return f"[File too large to inline: {att.get('filename')} ({size // 1024} KB) — set JIRA_MAX_ATTACHMENT_BYTES to increase limit]"

    if not content_url:
        return ""
    try:
        raw = client._download(content_url)
        return raw[:_MAX_ATTACHMENT_BYTES].decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug_structured(
            "Attachment download failed",
            extra_fields={"filename": att.get("filename"), "error": str(e)},
        )
        return ""


def fetch_issue_text_for_generate(issue_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch a Jira issue with full context for DITA dataset generation.

    Reads:
    - Issue metadata (key, type, status, priority, labels, components, fix versions)
    - Full description with all structured sections (steps to reproduce, expected/actual, environment)
    - All comments (up to 20, full text up to 2000 chars each)
    - Text/DITA/log attachments (up to 5 files, up to 80 KB each)
    - Attachment list with names/types for non-text files

    Returns:
        (formatted_text, None) on success
        (None, safe_error_message) on failure
    """
    key = _normalize_issue_key(issue_key)
    if not _issue_key_safe_for_api(key):
        return None, "Invalid issue key format."

    client = JiraClient()
    if not _jira_client_ready(client):
        logger.info_structured(
            "Jira shortcut skipped: client not configured",
            extra_fields={"issue_key": key},
        )
        return None, None

    # Fetch with attachment field included
    try:
        path = f"/rest/api/{client._api}/issue/{key}?fields=summary,description,labels,priority,status,issuetype,components,fixVersions,attachment,comment"
        issue = client._request("GET", path)
    except Exception as e:
        logger.warning_structured(
            "Jira fetch failed for generate-from-text",
            extra_fields={"issue_key": key, "error": str(e)},
        )
        return None, sanitize_error_for_generate(e)

    fields = issue.get("fields", {}) or {}
    summary = (fields.get("summary") or "").strip()
    description = (extract_description_from_issue(issue) or "").strip()
    labels = fields.get("labels") or []
    if not isinstance(labels, list):
        labels = []
    priority = ""
    pr = fields.get("priority")
    if isinstance(pr, dict) and pr.get("name"):
        priority = str(pr["name"])
    status = ""
    st = fields.get("status")
    if isinstance(st, dict) and st.get("name"):
        status = str(st["name"])
    issuetype = fields.get("issuetype")
    type_name = str(issuetype.get("name", "")) if isinstance(issuetype, dict) else ""

    components = [str(c["name"]) for c in (fields.get("components") or []) if isinstance(c, dict) and c.get("name")]
    fix_versions = [str(v["name"]) for v in (fields.get("fixVersions") or []) if isinstance(v, dict) and v.get("name")]

    # --- Comments: fetch up to 20, full body up to 2000 chars ---
    comment_lines: list[str] = []
    try:
        # Try embedded comment field first (avoids a second API call)
        embedded = fields.get("comment") or {}
        raw_comments = embedded.get("comments") or []
        if not raw_comments:
            raw_comments = client.get_issue_comments(key)
        from app.services.jira_client import _adf_to_plain_text as _adf
        for c in (raw_comments or [])[:_MAX_COMMENTS]:
            author = ""
            a = c.get("author") or c.get("updateAuthor") or {}
            if isinstance(a, dict):
                author = a.get("displayName") or a.get("name") or ""
            body_raw = c.get("body") or c.get("body_text") or ""
            if isinstance(body_raw, dict):
                body = _adf(body_raw)
            else:
                body = str(body_raw)
            body = body.strip()[:2000]
            if not body:
                continue
            created = str(c.get("created") or "")[:10]
            comment_lines.append(f"[{author or 'Unknown'} | {created}]: {body}")
    except Exception as e:
        logger.debug_structured(
            "Comments fetch skipped",
            extra_fields={"issue_key": key, "error": str(e)},
        )

    # --- Attachments: read text files, list others ---
    attachment_text_parts: list[str] = []
    attachment_list_parts: list[str] = []
    raw_attachments = fields.get("attachment") or []
    if isinstance(raw_attachments, list):
        # Sort: text/DITA first, then images, then others — read text ones first
        def _att_sort_key(a: dict) -> int:
            ext = "." + (a.get("filename") or "").lower().rsplit(".", 1)[-1]
            if ext in _TEXT_ATTACHMENT_EXTENSIONS:
                return 0
            if ext in _IMAGE_ATTACHMENT_EXTENSIONS:
                return 1
            return 2

        sorted_atts = sorted(raw_attachments, key=_att_sort_key)
        text_read = 0
        for att in sorted_atts[:20]:
            fname = att.get("filename") or "unknown"
            mime = att.get("mimeType") or ""
            size = int(att.get("size") or 0)
            ext = "." + fname.lower().rsplit(".", 1)[-1] if "." in fname else ""

            is_text_file = ext in _TEXT_ATTACHMENT_EXTENSIONS or mime.startswith("text/") or "xml" in mime
            is_image = ext in _IMAGE_ATTACHMENT_EXTENSIONS or mime.startswith("image/")

            if is_text_file and text_read < _MAX_ATTACHMENTS:
                content = _read_attachment_text(client, att)
                if content:
                    attachment_text_parts.append(
                        f"### Attachment: {fname} ({size // 1024 or 1} KB)\n{content}"
                    )
                    text_read += 1
                else:
                    attachment_list_parts.append(f"- {fname} ({mime}, {size // 1024 or 1} KB)")
            elif is_image:
                attachment_list_parts.append(f"- [Image] {fname} ({mime}, {size // 1024 or 1} KB)")
            else:
                attachment_list_parts.append(f"- {fname} ({mime}, {size // 1024 or 1} KB)")

    # --- Extract structured sections from description ---
    acceptance_criteria = _extract_section(description, r"(?:acceptance\s+criteria|ac)\s*[:\n]")
    steps_to_reproduce = _extract_section(description, r"(?:steps?\s+to\s+reproduce|reproduction\s+steps?|repro\s+steps?|how\s+to\s+reproduce)\s*[:\n]")
    expected_behavior = _extract_section(description, r"(?:expected\s+(?:behavior|result|outcome|output))\s*[:\n]")
    actual_behavior = _extract_section(description, r"(?:actual\s+(?:behavior|result|outcome|output)|current\s+behavior|actual\s+output)\s*[:\n]")
    environment = _extract_section(description, r"(?:environment|setup|config(?:uration)?|version|build)\s*[:\n]")
    notes = _extract_section(description, r"(?:additional\s+(?:notes?|info(?:rmation)?)|notes?|remarks?)\s*[:\n]")

    # --- Assemble the full context block ---
    parts = [
        f"Issue Key: {key}",
        f"Issue Type: {type_name}",
        f"Status: {status}",
        f"Priority: {priority}",
        f"Labels: {', '.join(str(x) for x in labels[:30]) or '(none)'}",
    ]
    if components:
        parts.append(f"Components: {', '.join(components[:10])}")
    if fix_versions:
        parts.append(f"Fix Versions: {', '.join(fix_versions[:10])}")

    parts.extend(["", "## Issue Summary", summary or "(no summary)", "", "## Issue Description"])
    # If we extracted structured sections, show the description without them to avoid duplication
    clean_description = description
    for pattern in [
        r"(?:steps?\s+to\s+reproduce|reproduction\s+steps?|repro\s+steps?).*",
        r"(?:expected\s+(?:behavior|result|outcome)).*",
        r"(?:actual\s+(?:behavior|result|outcome)|current\s+behavior).*",
        r"(?:environment|setup|config(?:uration)?).*",
        r"(?:acceptance\s+criteria|ac)\s*:.*",
    ]:
        pass  # keep full description — sections are also shown separately for emphasis
    parts.append(clean_description or "(no description)")

    if steps_to_reproduce:
        parts.extend(["", "## Steps to Reproduce", steps_to_reproduce])
    if expected_behavior:
        parts.extend(["", "## Expected Behavior", expected_behavior])
    if actual_behavior:
        parts.extend(["", "## Actual Behavior", actual_behavior])
    if environment:
        parts.extend(["", "## Environment", environment])
    if acceptance_criteria:
        parts.extend(["", "## Acceptance Criteria", acceptance_criteria])
    if notes:
        parts.extend(["", "## Additional Notes", notes])

    if attachment_list_parts or attachment_text_parts:
        parts.extend(["", "## Attachments"])
        if attachment_list_parts:
            parts.extend(attachment_list_parts)
        if attachment_text_parts:
            parts.extend(["", "### Attachment Contents"])
            parts.extend(attachment_text_parts)

    if comment_lines:
        parts.extend(["", f"## Comments ({len(comment_lines)})"])
        parts.extend(comment_lines)

    issue_text = "\n".join(parts)

    # Auto-index into ChromaDB in background so future similar issues benefit
    _auto_index_jira_background(key)

    return issue_text, None


def sanitize_error_for_generate(exc: Exception) -> str:
    """Short, non-sensitive message for chat tool result."""
    msg = str(exc).lower()
    if "404" in msg:
        return "Jira returned 404 for this issue. Check the key and API version (JIRA_API_VERSION=2 for some servers)."
    if "401" in msg or "403" in msg:
        return "Jira authentication failed. Check JIRA_BASE_URL and credentials in server .env."
    return "Could not fetch this issue from Jira. Paste the full issue text, or verify Jira configuration."


def _auto_index_jira_background(issue_key: str) -> None:
    """Index a single Jira issue into ChromaDB in a daemon thread — fire and forget."""
    import threading

    def _do_index():
        try:
            from app.services.jira_qa_index_service import (
                index_jql_to_chroma, _jira_configured, is_chroma_available, is_embedding_available,
            )
            from app.services.jira_client import JiraClient
            client = JiraClient()
            if not (_jira_configured(client) and is_chroma_available() and is_embedding_available()):
                return
            result = index_jql_to_chroma(
                f'issue = "{issue_key}"',
                limit=1,
                force_reindex=False,
                jira_client=client,
            )
            if result.get("chunks_upserted", 0) > 0:
                logger.info_structured(
                    "jira_auto_indexed",
                    extra_fields={"issue_key": issue_key, "chunks": result["chunks_upserted"]},
                )
        except Exception as exc:
            logger.debug_structured("jira_auto_index_skipped", extra_fields={"issue_key": issue_key, "error": str(exc)})

    threading.Thread(target=_do_index, daemon=True, name=f"jira-rag-{issue_key}").start()


def _get_similar_jiras(issue_key: str, issue_text: str, limit: int = 3) -> list[dict]:
    """Return top similar indexed Jira issues from ChromaDB (excluding the current issue)."""
    try:
        from app.services.jira_qa_retrieval_service import semantic_search_jira_qa, related_tickets_for_issue
        # Try direct related-tickets lookup first (uses pre-indexed metadata)
        related, _ = related_tickets_for_issue(issue_key, top_k=limit)
        if related:
            return related[:limit]
        # Fallback: semantic search on the issue text
        hits = semantic_search_jira_qa(issue_text[:500], top_k=limit + 1)
        return [h for h in (hits or []) if h.get("jira_key", "") != issue_key][:limit]
    except Exception:
        return []


def resolve_text_for_generate_from_text(body_text: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    If input contains a Jira issue key and Jira is configured, fetch the full issue
    (description, comments, attachments) and enrich with LLM DITA scenario analysis
    so the generation pipeline produces on-topic training data.

    Returns:
        (text_for_pipeline, jira_id_for_bundle_or_none, optional_warning)
    """
    raw = (body_text or "").strip()
    if not is_jira_shortcut_input(raw):
        key = extract_issue_key_from_generation_request(raw)
        if not key:
            return body_text, None, None
        formatted, err = fetch_issue_text_for_generate(key)
        if formatted:
            enriched = enrich_jira_text_with_analysis(formatted, issue_key=key)
            return f"{enriched}\n\n## Generation Request\n{raw}", key, None
        if err:
            return body_text, None, err
        return body_text, None, None

    key = extract_issue_key_from_shortcut(raw)
    if not key:
        return body_text, None, None

    formatted, err = fetch_issue_text_for_generate(key)
    if formatted:
        enriched = enrich_jira_text_with_analysis(formatted, issue_key=key)
        return enriched, key, None

    if err:
        return body_text, None, err

    return body_text, None, None


# ---------------------------------------------------------------------------
# Deep DITA analysis for dataset generation
# ---------------------------------------------------------------------------

_DITA_ANALYSIS_PROMPT = """You are a senior DITA architect whose job is to analyse a Jira bug/feature report and design a DITA XML training dataset for that specific scenario.

IMPORTANT: The goal is NOT to turn the Jira ticket into documentation.
The goal is to produce DITA XML training examples that cover the EXACT technical DITA scenario the ticket is about.

Read the Jira issue carefully, then:

1. **Identify the core DITA technical scenario** — What specific DITA elements, attributes, and mechanisms are broken or being tested? Be precise about the XML structure involved (e.g. "keydef in a keymap referenced via mapref processing-role=resource-only from a root map").

2. **Extract the specific DITA markup patterns** — What exact DITA XML does this scenario require?
   - Which elements: keydef, keyword, mapref, keyscope, topicref, etc.
   - Which attributes: keyref, keys, keyscope, processing-role, etc.
   - What map/topic structure is needed

3. **Design 5-8 specific DITA topic titles** that would form a training dataset for this exact scenario.
   Each title must:
   - Be directly about the DITA XML scenario from the Jira (not generic DITA concepts)
   - Reference the specific elements/attributes involved
   - Be useful as a training example for an AI learning DITA authoring

4. **Write a generation prompt** — a single paragraph that will be passed to a DITA content generator as "subject + context" to generate these specific topics.

Respond in this exact JSON format:
{
  "dita_scenario": "one precise paragraph describing the exact DITA XML scenario (elements, attributes, structure)",
  "dita_elements": ["keydef", "keyword", "mapref", ...],
  "dita_attributes": ["keyref", "keys", "keyscope", "processing-role", ...],
  "topic_titles": [
    {"title": "...", "type": "concept|task|reference", "dita_elements_used": ["keydef", "topicref"]},
    ...
  ],
  "subject": "specific 5-10 word DITA subject for dataset generation",
  "topic_family": "task|concept|topic",
  "generation_prompt": "paragraph describing what content to generate — mentions specific DITA elements, the scenario, what the topics should teach"
}"""


def analyze_jira_for_dita_dataset(issue_text: str, issue_key: str = "") -> dict:
    """Use LLM to reason deeply about a Jira issue and recommend DITA dataset topics.

    Returns a dict with keys: dita_concepts, authoring_scenario, root_cause_domain,
    topic_recommendations, subject, topic_family.
    Returns empty dict if LLM is unavailable or analysis fails.
    """
    from app.services.llm_service import is_llm_available
    if not is_llm_available() or not issue_text:
        return {}

    try:
        import asyncio
        import concurrent.futures
        import json as _json
        from app.services.llm_service import generate_text

        async def _run():
            return await generate_text(
                system_prompt=_DITA_ANALYSIS_PROMPT,
                user_prompt=f"Jira Issue {issue_key}:\n\n{issue_text[:int(os.getenv('JIRA_ANALYSIS_MAX_CHARS', '12000'))]}",
                max_tokens=1200,
                step_name="jira_dita_analysis",
            )

        # _build_generate_dita_preview_plan is sync but runs inside FastAPI's event loop.
        # asyncio.run() fails if a loop is already running — use a dedicated thread instead.
        try:
            asyncio.get_running_loop()
            # Inside a running loop: delegate to a thread with its own loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                raw = pool.submit(asyncio.run, _run()).result(timeout=45)
        except RuntimeError:
            # No running loop (e.g. standalone test / CLI)
            raw = asyncio.run(_run())

        raw = (raw or "").strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return _json.loads(raw[start:end])
    except Exception as e:
        # Warn so operators know the analysis was skipped — this silently degrades
        # dataset quality when the LLM times out or is unavailable.
        logger.warning_structured(
            "Jira DITA analysis failed — dataset generated without scenario analysis",
            extra_fields={"issue_key": issue_key, "error": str(e)},
        )
    return {}


def enrich_jira_text_with_analysis(issue_text: str, issue_key: str = "") -> str:
    """Append LLM-generated DITA scenario analysis to the Jira issue text.

    The analysis identifies the exact DITA elements/attributes involved,
    designs specific topic titles for the scenario, and appends a generation
    prompt that drives the content generator to produce on-topic training data.
    """
    analysis = analyze_jira_for_dita_dataset(issue_text, issue_key)

    # Append similar indexed Jiras as prior-art context
    similar = _get_similar_jiras(issue_key or "", issue_text[:400])

    if not analysis and not similar:
        return issue_text

    parts = [issue_text, "", "## DITA Dataset Analysis (AI Reasoned)"]

    # Prior-art: similar already-indexed Jira issues (from RAG)
    if similar:
        parts.extend(["", "### Similar Indexed Issues (Prior Art from RAG)"])
        for s in similar[:3]:
            jkey = s.get("jira_key", "")
            summary = (s.get("summary") or "")[:120]
            score = round(float(s.get("score") or 0), 2)
            parts.append(f"- [{jkey}] (similarity {score}) {summary}")
        parts.append(
            "Reference these similar issues when deciding topic structure — "
            "reuse validated dataset patterns from them where applicable."
        )

    if not analysis:
        return "\n".join(parts)

    scenario = analysis.get("dita_scenario", "")
    if scenario:
        parts.extend(["", "### Exact DITA Scenario", scenario])

    elements = analysis.get("dita_elements") or []
    attributes = analysis.get("dita_attributes") or []
    if elements:
        parts.extend(["", f"### DITA Elements: {', '.join(f'<{e}>' for e in elements[:10])}"])
    if attributes:
        parts.extend([f"### DITA Attributes: {', '.join(f'@{a}' for a in attributes[:10])}"])

    titles = analysis.get("topic_titles") or []
    if titles:
        parts.extend(["", "### Planned Topic Titles"])
        for t in titles[:8]:
            title = t.get("title", "")
            ttype = t.get("type", "topic")
            elems = ", ".join(f"<{e}>" for e in (t.get("dita_elements_used") or [])[:4])
            parts.append(f"- [{ttype.upper()}] {title}" + (f" (uses {elems})" if elems else ""))

    subject = analysis.get("subject", "")
    gen_prompt = analysis.get("generation_prompt", "")
    count = len(titles) or 5
    elements = analysis.get("dita_elements") or []
    root_cause = analysis.get("root_cause_domain", "")

    # Derive family from most common type in titles; prefer task > concept > reference
    _type_counts: dict = {}
    for t in titles:
        _type_counts[t.get("type", "topic")] = _type_counts.get(t.get("type", "topic"), 0) + 1
    _primary = max(_type_counts, key=_type_counts.get) if _type_counts else "task"
    topic_family = "task" if _primary in ("task", "topic") else _primary

    if subject:
        parts.extend(["", f"### Dataset Subject: {subject}"])

    # Detect keyref/keymap scenario — check BOTH the LLM analysis AND the raw issue text.
    # Direct text check is more reliable than LLM analysis (which can time out).
    _raw_issue_text = "\n".join(parts[:30])  # first part of the issue before our additions
    _KEYREF_TEXT_RE = re.compile(
        r"\b(keydef|keyref|keyscope|key\s+def(?:inition)?|keyword.*keyref|keyref.*keyword"
        r"|keys?\s+map|keymap|insert.*keyword|keyword.*insert|key\s+reference"
        r"|\bkeys\b.*\bmap\b|\broot\s+map\b.*\bkeys\b)\b",
        re.IGNORECASE,
    )
    _direct_keyref = bool(_KEYREF_TEXT_RE.search(_raw_issue_text) or _KEYREF_TEXT_RE.search(issue_key or ""))
    _keyref_scenario = (
        _direct_keyref  # direct text match (most reliable)
        or root_cause == "key_resolution"
        or any(e.lower() in ("keyword", "keydef", "keyref", "keyscope", "mapref") for e in elements)
        or "keyref" in (gen_prompt or "").lower()
        or "keydef" in (gen_prompt or "").lower()
    )

    if _keyref_scenario:
        # Build a targeted keydef dataset request: keys map + topics using <keyword keyref>
        parts.extend([
            "",
            "## Suggested Generation",
            f"Generate a keydef dataset for: {subject}.",
            "",
            "Dataset requirements (DITA keyref scenario):",
            "- Create a DITA keys map (keys.ditamap) with 6-8 <keydef> entries representing",
            "  real AEM Guides terms: product-name, feature-keyword-insert, root-map-path,",
            "  keymap-filename, web-editor-name, insert-keyword-action, key-resolution-context.",
            "- Create a root DITA map that references the keys map via",
            "  <mapref href='keys.ditamap' processing-role='resource-only'/>",
            "- Create 4-5 topics that USE those keys — each topic body must contain",
            "  <keyword keyref='keyname'/> elements inline in <p>, <cmd>, or <title> elements.",
            "- This is a keydef training dataset: the topics must DEMONSTRATE keyword insertion",
            "  with keyref, not just describe it.",
            (gen_prompt or "")[:500],
        ])
    else:
        # Standard: contract builder reads this to determine family + count
        parts.extend([
            "",
            "## Suggested Generation",
            f"Generate {count} {topic_family} topics about: {subject}.",
            (gen_prompt or "")[:1000],
        ])

    return "\n".join(parts)
